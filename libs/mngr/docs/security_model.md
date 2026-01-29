# Security Model

`mngr` runs code in isolated hosts. The security of that isolation depends on your choice of [provider](./concepts/providers.md).

## Trust Model

**Plugins** are fully trusted. They execute with your privileges and can access your files, credentials, and network. Only install plugins from sources you trust.

**Providers** are trusted to enforce isolation between hosts and to honestly report host state. They will technically have access to files written to disk and in-memory state, and thus are assumed to be highly trusted.

**Hosts** are containers within which is can be *possible* to run untrusted code. The security of that isolation depends on the provider. For example, a Docker-based provider [future] relies on Docker's isolation mechanisms, which are generally strong but not infallible. A cloud-based VM provider relies on the cloud provider's hypervisor security. Local hosts have no isolation and should only run fully trusted code. The user is responsible for deciding which information and permissions [future] to grant to a host / the agents on a host.

Note that **all** hosts can end up running until you call `mngr enforce` [future] (because the idle detection script [future] runs inside the host). Thus, untrusted code could potentially run indefinitely unless there is external enforcement of the idle policies (which can be done via `mngr enforce`).

**Agents** on the same host are assumed to all have full access to all information and capabilities on the host. If you want isolation, use a separate host and restrict what information is shared with that host. The permissions and limits for a host are the **union** of all agents on that host.

