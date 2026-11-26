"""Local transaction hooks used by installed checkout operations."""

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from skm.modules.workspace.domain.checkout_binding import ObservedCheckout
from skm.modules.workspace.generated.queries import MatchCheckout
from skm.modules.workspace.generated.views import AttachDecisionView


class CheckoutTransaction(Protocol):
    @property
    def locator(self) -> str: ...

    def match(self, query: MatchCheckout) -> AttachDecisionView: ...

    def dispatch(self, step: str, command: object) -> object: ...

    def has_step(self, step: str) -> bool: ...

    def bound(
        self, workspace_id: UUID, project_id: UUID, repository_id: UUID, binding_id: UUID, mount: str
    ) -> None: ...


type BeginCheckout = Callable[[ObservedCheckout], CheckoutTransaction]
type VerifyCheckoutRoot = Callable[[str, UUID], str]
type BeginVerification = Callable[[str, ObservedCheckout], CheckoutTransaction]
