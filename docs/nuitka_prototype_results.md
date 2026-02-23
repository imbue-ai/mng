# Nuitka Compilation Prototype: Results

## Goal

Evaluate whether compiling `mng` with [Nuitka](https://nuitka.net/) (a Python-to-C compiler) reduces CLI startup latency.

## Setup

- Nuitka 4.0.1, standalone mode with `--follow-imports`
- Compiled entry point: `imbue.mng.main:cli`
- Included package data for: coolname, imbue.mng.resources, certifi
- Backend C compiler: gcc 11
- Resulting binary: 143MB standalone (220MB total dist directory)
- Build time: ~10 minutes (without ccache)

## Results

All times are wall-clock averages of 3 runs.

### `--help` (measures import + plugin load + help format, no I/O)

| Method               | Real time | User time |
|----------------------|-----------|-----------|
| Nuitka standalone    | 1.097s    | 0.985s    |
| `uv run mng`        | 1.088s    | 0.925s    |
| Direct Python        | 1.040s    | 0.870s    |

### `list` (full command with provider queries)

| Method               | Real time | User time |
|----------------------|-----------|-----------|
| Nuitka standalone    | 1.993s    | 1.051s    |
| `uv run mng`        | 1.950s    | 1.013s    |

### Baselines

| Measurement                        | Time   |
|------------------------------------|--------|
| Python interpreter startup         | 0.012s |
| `uv run` overhead                  | 0.045s |
| Importing `imbue.mng.main`         | 0.850s |

## Conclusion

**Nuitka provides no meaningful startup improvement for `mng`.**

The compiled binary is within noise of interpreted Python (~1.1s vs ~1.0s for `--help`). This is because the bottleneck is Python's import machinery loading heavy dependency trees, not bytecode interpretation speed. Nuitka compiles Python to C but still must execute the same module-level initialization code for every imported package.

## Where the time actually goes

Import profiling (`python -X importtime`) shows the top contributors to the ~850ms import time:

| Import                           | Cumulative time |
|----------------------------------|-----------------|
| `imbue.mng.interfaces.data_types`| 149ms           |
| `pyinfra`                        | 133ms           |
| `modal`                          | 104ms           |
| `imbue.mng.cli.cleanup`         | 84ms            |
| `docker`                         | 48ms            |
| `attrs`                          | 53ms            |
| `urwid`                          | 34ms            |

These are all heavyweight packages that perform significant work at import time (metaclass setup, protobuf compilation, C extension loading, etc.). Nuitka cannot optimize away this work.

## Recommended alternatives

To actually reduce `mng` startup time, consider:

1. **Lazy imports**: Defer heavy imports (`modal`, `pyinfra`, `docker`, `urwid`) until the specific command that needs them is invoked. For example, `mng list` doesn't need `pyinfra` or `urwid` at all. This could save 200-400ms.

2. **Plugin-level lazy loading**: The plugin/provider registry currently imports all backends at module load time. Loading only the backends relevant to the current command (or the user's configured providers) would help.

3. **Import restructuring**: Some internal modules (e.g., `interfaces.data_types` at 149ms) pull in heavy dependencies transitively. Breaking these dependency chains could reduce import time.

4. **`uv run` bypass**: For users who run `mng` frequently, installing it directly (rather than going through `uv run` each time) saves ~45ms. This is minor but free.
