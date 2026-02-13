"""SSH utilities for Modal provider.

Re-exports from the shared ssh_utils module for backward compatibility.
"""

from imbue.mngr.providers.ssh_utils import add_host_to_known_hosts as add_host_to_known_hosts
from imbue.mngr.providers.ssh_utils import generate_ed25519_host_keypair as generate_ed25519_host_keypair
from imbue.mngr.providers.ssh_utils import generate_ssh_keypair as generate_ssh_keypair
from imbue.mngr.providers.ssh_utils import load_or_create_host_keypair as load_or_create_host_keypair
from imbue.mngr.providers.ssh_utils import load_or_create_ssh_keypair as load_or_create_ssh_keypair
from imbue.mngr.providers.ssh_utils import save_ssh_keypair as save_ssh_keypair
