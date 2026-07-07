# Contributing to Drone Storage Bench

Thank you for your interest in contributing to Drone Storage Bench! This document outlines our setup steps, code quality rules, and development practices.

---

## 🛠️ Local Development Setup

We use [uv](https://github.com/astral-sh/uv) for fast, predictable Python package and dependency management.

1. **Clone the repository**:
   ```bash
   git clone https://github.com/TagoreNandan/drone-storage-bench.git
   cd drone-storage-bench
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Verify the installation**:
   Ensure you can run the test suite successfully:
   ```bash
   uv run pytest
   ```

---

## 🧪 Code Quality Guidelines

We enforce strict style checks and type checks. Before opening a pull request, make sure the following checks pass:

### Code Formatting and Linting
We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:
```bash
# Run style check
uv run ruff check .

# Automatically apply safe fixes
uv run ruff check --fix .

# Verify formatting style
uv run ruff format --check .
```

### Static Type Checks
We enforce strict typing with `mypy`:
```bash
uv run mypy src/ tests/
```

### Running Tests
Always run the test suite to prevent regressions:
```bash
uv run pytest
```

---

## 🚀 Submitting Pull Requests

1. Create a new feature branch: `git checkout -b feature/your-feature-name`.
2. Commit your changes with descriptive messages.
3. Ensure all local tests and code style checks pass successfully.
4. Push your branch and open a Pull Request against `main`.
