# One image for both services: the FastAPI backend and the Streamlit frontend.
FROM python:3.12-slim

# uv installs the exact versions from uv.lock, fast and reproducible
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first: this layer is cached as long as pyproject.toml and uv.lock stay the same
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the code, fixtures and notes. The project itself is installed in editable mode,
# so PROJECT_ROOT points to /app and the app finds data/ and knowledge/.
COPY src ./src
COPY app ./app
COPY knowledge ./knowledge
COPY data/fixtures ./data/fixtures
COPY .streamlit ./.streamlit
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000 8501

# Default: the backend. docker-compose starts the frontend with its own command.
CMD ["uvicorn", "o2c.api:app", "--host", "0.0.0.0", "--port", "8000"]
