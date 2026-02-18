# Provider Backends

A [provider instance](./providers.md) is a configured instance of a **"provider backend"** that creates and manages [hosts](./hosts.md).

A "provider backend" (like `docker`, `modal`, or `aws`) defines a *parameterized* way to create and manage hosts. A *provider instance* is a configured endpoint of that backend.

This lets you have multiple provider instances of the same backend: multiple Modal accounts, AWS accounts, remote Docker hosts, or even remote `mngr` instances that manage their own local agents.

## Built-in Provider Backends

Each provider backend has different trade-offs:

|                         |     Local      |      Docker       |       Modal        |
|-------------------------|:--------------:|:-----------------:|:------------------:|
| **Cost**                |      Free      |       Free        |    Pay-per-use     |
| **Setup**               |      None      |  Install Docker   |   Modal account    |
| **Isolation**           |     ❌ None     |   🔶 Container    |     ✅ Full VM      |
| **Performance**         |    ✅ Native    |   ✅ Near-native   | 🔶 Network latency |
| **Accessible anywhere** |       ❌        |         ❌         |         ✅          |
| **Snapshots**           |       ❌        | ✅ `docker commit` |      ✅ Native      |
| **Resource limits**     |       ❌        |     ✅ cgroups     |      ✅ Native      |
| **GPU support**         | ✅ If available | 🔶 Requires setup |    ✅ On-demand     |

**When to use each:**

- **Local**: Fast iteration with trusted agents. No overhead, but no isolation.
- **Docker** [future]: Isolation without cloud costs. Good for untrusted agents on your machine.
- **Modal**: Full isolation in the cloud. Best for untrusted agents or long-running work. Access from anywhere.
- **SSH**: For connecting to another provider via SSH (e.g., a remote machine running its own `mngr` instance).

## Custom Provider Backends

Browse [100's of additional plugins](http://imbue.com/mngr/plugins) [future] for other provider backends (like AWS [future], GCP, Kubernetes, etc.).

You can also create custom plugins to register additional provider backends by calling `register_provider_backend(...)` in the plugin's `on_startup` hook
