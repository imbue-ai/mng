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

test-unit:
  uv run pytest --ignore-glob="**/test_*.py" --cov-fail-under=36

test-integration:
  uv run pytest

# can run without coverage to make things slightly faster when checking locally
test-quick:
  uv run pytest --no-cov --cov-fail-under=0

test-acceptance:
  # when running these locally, we set the max duration super high just so that we don't fail (which makes it harder to see the errors)
  PYTEST_MAX_DURATION=600 uv run pytest --override-ini='cov-fail-under=0' --no-cov -n 4 -m "no release"

test-release:
  # when running these locally, we set the max duration super high just so that we don't fail (which makes it harder to see the errors)
  PYTEST_MAX_DURATION=1200 1 uv run pytest --override-ini='cov-fail-under=0' --no-cov -n 4 -m "acceptance or not acceptance"

# Generate test timings for pytest-split (run periodically to keep timings up to date. Runs all acceptance and release)
test-timings:
  # when running these locally, we set the max duration super high just so that we don't fail (which makes it harder to see the errors)
  PYTEST_MAX_DURATION=6000 uv run pytest --override-ini='cov-fail-under=0' --no-cov -n 0 -m "acceptance or not acceptance" --store-durations

# useful for running against a single test, regardless of how it is marked
test target:
  PYTEST_MAX_DURATION=600 uv run pytest --override-ini='cov-fail-under=0' --no-cov -n 0 -m "acceptance or not acceptance" "{{target}}"
