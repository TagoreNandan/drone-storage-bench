from pydantic import BaseModel

from benchmark.config.settings import ScoringWeightsConfig
from benchmark.core.specification import (
    BenchmarkResult,
    BenchmarkSuite,
    MetricType,
    ScenarioType,
)

# Maps scenario types to their primary metric.
# True = higher metric is better, False = lower metric is better.
PRIMARY_METRIC_MAPPING = {
    ScenarioType.WRITE_THROUGHPUT: (MetricType.ROWS_PER_SECOND, True),
    ScenarioType.BURST_WRITE_LATENCY: (MetricType.AVERAGE_LATENCY_MS, False),
    ScenarioType.TIME_RANGE_QUERIES: (MetricType.AVERAGE_LATENCY_MS, False),
    ScenarioType.AGGREGATION_QUERIES: (MetricType.AVERAGE_LATENCY_MS, False),
    ScenarioType.HISTORICAL_REPLAY: (MetricType.REPLAY_THROUGHPUT_ROWS_PER_SECOND, True),
    ScenarioType.COMPRESSION_EVALUATION: (MetricType.COMPRESSION_RATIO, True),
    ScenarioType.JOIN_EVALUATION: (MetricType.AVERAGE_LATENCY_MS, False),
}

# Scenario type to weight name mapping
SCENARIO_WEIGHT_MAPPING = {
    ScenarioType.WRITE_THROUGHPUT: "sustained_write_throughput",
    ScenarioType.BURST_WRITE_LATENCY: "burst_latency",
    ScenarioType.TIME_RANGE_QUERIES: "time_range_queries",
    ScenarioType.AGGREGATION_QUERIES: "aggregation_queries",
    ScenarioType.HISTORICAL_REPLAY: "historical_replay",
    ScenarioType.COMPRESSION_EVALUATION: "compression",
    ScenarioType.JOIN_EVALUATION: "join_evaluation",
}


class ScenarioScore(BaseModel):
    """Score for a specific database and scenario."""

    database: str
    scenario: str
    scenario_type: str
    metric_type: str
    raw_value: float | None
    normalized_score: float
    weighted_score: float


class DatabaseScore(BaseModel):
    """Aggregated score profile and scenario scores for a database."""

    database: str
    overall_score: float
    scenario_scores: list[ScenarioScore]
    rank: int


class ScoringReport(BaseModel):
    """Overall comparative scoring report for a benchmark suite run."""

    database_scores: list[DatabaseScore]
    scoring_weights: dict[str, float]


class ScoringEngine:
    """Computes multi-dimensional database performance indices.

    Normalizes throughput, latency, and storage statistics using relative min-max range
    evaluations, computes overall weighted rankings, and outputs strongly typed reports.
    """

    def __init__(
        self,
        weights: ScoringWeightsConfig | dict[str, float] | None = None,
    ) -> None:
        """Initialize scoring criteria and coefficients."""
        if weights is None:
            self.weights = {
                "sustained_write_throughput": 0.20,
                "burst_latency": 0.15,
                "time_range_queries": 0.15,
                "aggregation_queries": 0.15,
                "historical_replay": 0.15,
                "compression": 0.10,
                "join_evaluation": 0.10,
            }
        elif isinstance(weights, dict):
            self.weights = weights
        else:
            self.weights = weights.model_dump()

    def score(self, results: list[BenchmarkResult], suite: BenchmarkSuite) -> ScoringReport:
        """Computes comparative scores and rankings for all participating databases.

        Args:
            results: list of BenchmarkResult objects collected from workloads.
            suite: The BenchmarkSuite scenario blueprint.

        Returns:
            ScoringReport containing database overall scores, scenario cards, and ranks.
        """
        # Find all unique database names in results
        databases = sorted({r.database_name for r in results})

        # If no databases ran, return empty report
        if not databases or not suite.scenarios:
            return ScoringReport(database_scores=[], scoring_weights=self.weights)

        # 1. Normalize weights for scenarios active in this suite
        active_weights = {}
        for scenario in suite.scenarios:
            w_name = SCENARIO_WEIGHT_MAPPING.get(scenario.scenario_type)
            if w_name:
                active_weights[scenario.scenario_type] = self.weights.get(w_name, 0.0)
            else:
                active_weights[scenario.scenario_type] = 0.0

        weight_sum = sum(active_weights.values())
        normalized_weights = {}
        for s_type, w_val in active_weights.items():
            normalized_weights[s_type] = w_val / weight_sum if weight_sum > 0.0 else 0.0

        # Map to store compiled scores per database
        db_overall = dict.fromkeys(databases, 0.0)
        db_scenario_cards: dict[str, list[ScenarioScore]] = {db: [] for db in databases}

        # 2. Score each scenario sequentially
        for scenario in suite.scenarios:
            s_type = scenario.scenario_type
            metric_info = PRIMARY_METRIC_MAPPING.get(s_type)
            if not metric_info:
                # Fallback if scenario type is unknown
                continue

            metric_type, higher_is_better = metric_info

            # Retrieve raw metric values for each database
            raw_values: dict[str, float] = {}
            for res in results:
                if res.scenario_name != scenario.name or not res.success:
                    continue
                # Locate primary metric value
                for m in res.metrics:
                    if m.metric_type == metric_type:
                        raw_values[res.database_name] = m.value
                        break

            # Find range across successful databases
            if raw_values:
                min_val = min(raw_values.values())
                max_val = max(raw_values.values())
            else:
                min_val = max_val = 0.0

            # Calculate scores for each database
            for db in databases:
                # Check if this database has a valid raw value
                if db in raw_values:
                    val = raw_values[db]
                    # Range checks to prevent division by zero
                    if max_val == min_val:
                        norm_score = 100.0
                    else:
                        if higher_is_better:
                            norm_score = ((val - min_val) / (max_val - min_val)) * 100.0
                        else:
                            norm_score = ((max_val - val) / (max_val - min_val)) * 100.0
                else:
                    val = None
                    norm_score = 0.0

                w_factor = normalized_weights.get(s_type, 0.0)
                weighted_score = norm_score * w_factor

                # Accumulate overall score
                db_overall[db] += weighted_score

                # Save scenario score card
                db_scenario_cards[db].append(
                    ScenarioScore(
                        database=db,
                        scenario=scenario.name,
                        scenario_type=s_type.value,
                        metric_type=metric_type.value,
                        raw_value=val,
                        normalized_score=norm_score,
                        weighted_score=weighted_score,
                    )
                )

        # 3. Compile DatabaseScore cards and sort deterministically
        db_scores = []
        for db in databases:
            db_scores.append(
                DatabaseScore(
                    database=db,
                    overall_score=db_overall[db],
                    scenario_scores=db_scenario_cards[db],
                    rank=0,
                )
            )

        # Secondary sort key (database name alphabetical) guarantees deterministic ranking on ties
        db_scores.sort(key=lambda x: (-x.overall_score, x.database))

        # Assign ranks using standard competition ranking rules (1, 1, 3)
        current_rank = 1
        for i, score_card in enumerate(db_scores):
            if i > 0 and score_card.overall_score < db_scores[i - 1].overall_score:
                current_rank = i + 1
            score_card.rank = current_rank

        return ScoringReport(database_scores=db_scores, scoring_weights=self.weights)
