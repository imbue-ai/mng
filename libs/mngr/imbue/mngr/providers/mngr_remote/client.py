from typing import Any

import httpx
from loguru import logger
from pydantic import SecretStr

from imbue.mngr.errors import ProviderError


class MngrRemoteClient:
    """HTTP client for communicating with a remote mngr API server."""

    _base_url: str
    _token: SecretStr

    def __init__(self, base_url: str, token: SecretStr) -> None:
        object.__setattr__(self, "_base_url", base_url.rstrip("/"))
        object.__setattr__(self, "_token", token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token.get_secret_value()}",
            "Content-Type": "application/json",
        }

    def list_agents(self) -> list[dict[str, Any]]:
        """Fetch the agent list from the remote API server."""
        url = f"{self._base_url}/api/agents"
        try:
            response = httpx.get(url, headers=self._headers(), timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data.get("agents", [])
        except httpx.HTTPError as e:
            logger.warning("Failed to fetch agents from remote mngr at {}: {}", self._base_url, e)
            raise ProviderError(f"Failed to connect to remote mngr API at {self._base_url}: {e}") from e

    def send_message(self, agent_id: str, message: str) -> None:
        """Send a message to an agent on the remote server."""
        url = f"{self._base_url}/api/agents/{agent_id}/message"
        try:
            response = httpx.post(url, headers=self._headers(), json={"message": message}, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"Failed to send message to agent {agent_id}: {e}") from e

    def stop_agent(self, agent_id: str) -> None:
        """Stop an agent on the remote server."""
        url = f"{self._base_url}/api/agents/{agent_id}/stop"
        try:
            response = httpx.post(url, headers=self._headers(), timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"Failed to stop agent {agent_id}: {e}") from e

    def record_activity(self, agent_id: str) -> None:
        """Record activity for an agent on the remote server."""
        url = f"{self._base_url}/api/agents/{agent_id}/activity"
        try:
            response = httpx.post(url, headers=self._headers(), json={}, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.debug("Failed to record activity for agent {}: {}", agent_id, e)
