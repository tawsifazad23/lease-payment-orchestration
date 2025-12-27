# Contributing

Thank you for your interest in contributing to the Lease Payment Orchestration System!

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/your-username/lease-payment-orchestration.git`
3. Create a feature branch: `git checkout -b feature/your-feature`
4. Make your changes
5. Test your changes: `pytest tests/ -v`
6. Commit with clear messages: `git commit -m "feat: add your feature"`
7. Push to your fork: `git push origin feature/your-feature`
8. Open a pull request against `main`

## Development Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=services --cov=shared
```

## Testing Requirements

- All tests must pass: `pytest tests/ -v`
- Code coverage should not decrease
- New features must include tests
- Tests should follow existing patterns

## Code Style

- Format code with Black: `black services/ shared/ tests/`
- Check with flake8: `flake8 services/ shared/ tests/`
- Sort imports with isort: `isort services/ shared/ tests/`

## Commit Messages

Follow conventional commits:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `test:` - Tests
- `refactor:` - Code refactoring
- `perf:` - Performance improvement

Example: `feat: add payment retry mechanism`

## Pull Request Process

1. Update documentation for any API changes
2. Ensure all tests pass
3. Add tests for new functionality
4. Request review from maintainers
5. Address feedback and update PR

## Questions?

Open an issue or discussion thread in the repository.
