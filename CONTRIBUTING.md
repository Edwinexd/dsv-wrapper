# Contributing to DSV Wrapper

Thank you for your interest in contributing to DSV Wrapper! This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful and constructive in all interactions. We aim to maintain a welcoming environment for all contributors.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue with:
- A clear description of the problem
- Steps to reproduce the issue
- Expected vs actual behavior
- Your environment (Python version, OS, etc.)
- Any relevant error messages or stack traces

### Suggesting Enhancements

Feature requests are welcome! When suggesting an enhancement:
- Clearly describe the proposed feature
- Explain the use case and why it would be valuable
- Consider implementation details if possible

### Pull Requests

1. **Fork the repository** and create a new branch for your changes
2. **Make your changes** following the coding standards below
3. **Test your changes** thoroughly
4. **Update documentation** if needed
5. **Submit a pull request** with a clear description of your changes

#### Pull Request Guidelines

- Keep changes focused on a single feature or bug fix
- Write clear, descriptive commit messages
- Ensure all tests pass
- Add tests for new functionality
- Update the README or documentation if needed

## Development Setup

```bash
# Clone your fork
git clone <your-fork-url>
cd dsv-wrapper

# Create a virtual environment
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

## Coding Standards

### Python Style

- Follow [PEP 8](https://pep8.org/) style guidelines
- Use type hints for function parameters and return values
- Maximum line length: 88 characters (Black default)
- Use descriptive variable and function names

### Code Formatting

We use [Black](https://black.readthedocs.io/) for code formatting:

```bash
# Format all code
black dsv_wrapper/

# Check formatting without making changes
black --check dsv_wrapper/
```

### Linting

We use [Ruff](https://docs.astral.sh/ruff/) for linting:

```bash
# Check for linting issues
ruff check dsv_wrapper/

# Auto-fix issues where possible
ruff check --fix dsv_wrapper/
```

### Type Checking

We use type hints throughout the codebase. Consider using [mypy](http://mypy-lang.org/) for type checking:

```bash
mypy dsv_wrapper/
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=dsv_wrapper

# Run specific test file
pytest tests/test_auth.py

# Run with verbose output
pytest -v
```

### Writing Tests

- Write tests for all new functionality
- Place tests in the `tests/` directory
- Use descriptive test names that explain what is being tested
- Use pytest fixtures for common setup
- Mock external dependencies (HTTP requests, etc.)

Example test structure:

```python
import pytest
from dsv_wrapper import DaisyClient

def test_schedule_retrieval():
    """Test that schedule retrieval returns valid data."""
    # Setup
    client = DaisyClient(username="test", password="test")

    # Execute
    schedule = client.get_schedule(...)

    # Assert
    assert schedule is not None
    assert len(schedule.rooms) > 0
```

## Project Structure

```
dsv-wrapper/
├── dsv_wrapper/         # Main package
│   ├── __init__.py      # Package exports
│   ├── auth/            # Authentication module
│   ├── models.py        # Pydantic models
│   ├── daisy.py         # Daisy client
│   ├── handledning.py   # Handledning client
│   ├── client.py        # Unified client
│   ├── utils.py         # Utilities
│   └── exceptions.py    # Custom exceptions
├── tests/               # Test files
├── examples/            # Example scripts
└── docs/               # Documentation
```

## Commit Messages

Write clear, concise commit messages:

- Use present tense ("Add feature" not "Added feature")
- First line should be 50 characters or less
- Reference issues and pull requests where appropriate

Examples:
```
Add support for room availability filtering
Fix authentication cookie expiration handling
Update documentation for async client usage
```

## Dependencies

- Keep dependencies minimal and well-justified
- Update `requirements.txt` when adding new dependencies
- Pin versions for reproducibility
- Add development dependencies to `pyproject.toml` under `[project.optional-dependencies]`

## Documentation

- Update docstrings for all public functions and classes
- Use Google-style docstrings
- Include parameter types and return types
- Provide usage examples in docstrings for complex functionality

Example:

```python
def book_room(
    self,
    room_id: str,
    schedule_date: date,
    start_time: time,
    end_time: time,
    purpose: str
) -> BookingSlot:
    """Book a room for a specific time slot.

    Args:
        room_id: The unique identifier for the room
        schedule_date: The date for the booking
        start_time: Start time of the booking
        end_time: End time of the booking
        purpose: Purpose or description of the booking

    Returns:
        BookingSlot object containing booking details

    Raises:
        RoomNotAvailableError: If the room is already booked
        AuthenticationError: If authentication fails
    """
```

## License

By contributing to DSV Wrapper, you agree that your contributions will be licensed under the GNU General Public License v3.0.

## Questions?

If you have questions about contributing, feel free to open an issue for discussion.
