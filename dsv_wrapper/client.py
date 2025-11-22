"""Unified client for all DSV systems."""

from typing import Optional

from .actlab import ACTLabClient, AsyncACTLabClient
from .daisy import AsyncDaisyClient, DaisyClient
from .handledning import AsyncHandledningClient, HandledningClient


class DSVClient:
    """Unified synchronous client for all DSV systems."""

    def __init__(
        self,
        username: str,
        password: str,
        daisy_service: str = "daisy_staff",
        use_cache: bool = True,
    ):
        """Initialize DSV unified client.

        Args:
            username: SU username
            password: SU password
            daisy_service: Daisy service type (daisy_staff or daisy_student)
            use_cache: Whether to cache authentication cookies
        """
        self.username = username
        self.password = password
        self.use_cache = use_cache

        # Initialize clients
        self._daisy: Optional[DaisyClient] = None
        self._handledning: Optional[HandledningClient] = None
        self._actlab: Optional[ACTLabClient] = None
        self.daisy_service = daisy_service

    @property
    def daisy(self) -> DaisyClient:
        """Get Daisy client (lazy initialization).

        Returns:
            DaisyClient instance
        """
        if self._daisy is None:
            self._daisy = DaisyClient(
                username=self.username,
                password=self.password,
                service=self.daisy_service,
                use_cache=self.use_cache,
            )
        return self._daisy

    @property
    def handledning(self) -> HandledningClient:
        """Get Handledning client (lazy initialization).

        Returns:
            HandledningClient instance
        """
        if self._handledning is None:
            self._handledning = HandledningClient(
                username=self.username,
                password=self.password,
                mobile=False,
                use_cache=self.use_cache,
            )
        return self._handledning

    @property
    def actlab(self) -> ACTLabClient:
        """Get ACT Lab client (lazy initialization).

        Returns:
            ACTLabClient instance
        """
        if self._actlab is None:
            self._actlab = ACTLabClient(
                username=self.username,
                password=self.password,
                use_cache=self.use_cache,
            )
        return self._actlab

    def close(self) -> None:
        """Close all client sessions."""
        if self._daisy is not None:
            self._daisy.close()
        if self._handledning is not None:
            self._handledning.close()
        if self._actlab is not None:
            self._actlab.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class AsyncDSVClient:
    """Unified asynchronous client for all DSV systems."""

    def __init__(
        self,
        username: str,
        password: str,
        daisy_service: str = "daisy_staff",
        use_cache: bool = True,
    ):
        """Initialize async DSV unified client.

        Args:
            username: SU username
            password: SU password
            daisy_service: Daisy service type (daisy_staff or daisy_student)
            use_cache: Whether to cache authentication cookies
        """
        self.username = username
        self.password = password
        self.use_cache = use_cache

        # Initialize clients
        self._daisy: Optional[AsyncDaisyClient] = None
        self._handledning: Optional[AsyncHandledningClient] = None
        self._actlab: Optional[AsyncACTLabClient] = None
        self.daisy_service = daisy_service

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._daisy is not None:
            await self._daisy.__aexit__(exc_type, exc_val, exc_tb)
        if self._handledning is not None:
            await self._handledning.__aexit__(exc_type, exc_val, exc_tb)
        if self._actlab is not None:
            await self._actlab.__aexit__(exc_type, exc_val, exc_tb)

    async def get_daisy(self) -> AsyncDaisyClient:
        """Get async Daisy client (lazy initialization).

        Returns:
            AsyncDaisyClient instance
        """
        if self._daisy is None:
            self._daisy = AsyncDaisyClient(
                username=self.username,
                password=self.password,
                service=self.daisy_service,
                use_cache=self.use_cache,
            )
            await self._daisy.__aenter__()
        return self._daisy

    async def get_handledning(self) -> AsyncHandledningClient:
        """Get async Handledning client (lazy initialization).

        Returns:
            AsyncHandledningClient instance
        """
        if self._handledning is None:
            self._handledning = AsyncHandledningClient(
                username=self.username,
                password=self.password,
                mobile=False,
                use_cache=self.use_cache,
            )
            await self._handledning.__aenter__()
        return self._handledning

    async def get_actlab(self) -> AsyncACTLabClient:
        """Get async ACT Lab client (lazy initialization).

        Returns:
            AsyncACTLabClient instance
        """
        if self._actlab is None:
            self._actlab = AsyncACTLabClient(
                username=self.username,
                password=self.password,
                use_cache=self.use_cache,
            )
            await self._actlab.__aenter__()
        return self._actlab
