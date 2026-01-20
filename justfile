build target:
  @if [ "{{target}}" = "flexmux" ]; then \
    cd libs/flexmux/frontend && pnpm install && pnpm run build; \
  elif [ "{{target}}" = "claude_web_view" ]; then \
    cd apps/claude_web_view/frontend && pnpm install && pnpm run build; \
  elif [ -d "apps/{{target}}" ]; then \
    uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/{{target}}; \
  elif [ -d "libs/{{target}}" ]; then \
    uvx --from build pyproject-build --installer=uv --outdir=dist --wheel libs/{{target}}; \
  else \
    echo "Error: Target '{{target}}' not found in apps/ or libs/"; \
    exit 1; \
  fi

run target:
  @if [ "{{target}}" = "flexmux" ]; then \
    uv run flexmux; \
  else \
    echo "Error: No run command defined for '{{target}}'"; \
    exit 1; \
  fi

alias test := test-integration

test-unit:
  uv run pytest --ignore-glob="**/test_*.py" --cov-fail-under=36

test-integration:
  uv run pytest

test-acceptance:
  uv run pytest --override-ini='addopts=-n 4 --durations=20 --durations-min=1.0' --no-cov

# Generate test timings for pytest-split (run periodically to keep timings up to date. Runs all acceptance tests as well)
test-timings:
  PYTEST_MAX_DURATION=600 uv run pytest -n 0 --store-durations --no-cov --cov-fail-under=0 --override-ini='addopts=-n 0 --durations=20 --durations-min=15.0'
