"""Multi-account state tracking and quota rotation for Google AI Studio."""

import json
import logging
import os
import time
from typing import Dict, List, Optional

logger = logging.getLogger("virel.webhook")

DEFAULT_COOLDOWN_SECONDS = 6 * 3600  # 6 hours default


class Account:
    """Represents a Google account instance (via authuser index or distinct profile)."""

    def __init__(
        self,
        account_id: str,
        profile_dir: str,
        authuser: Optional[int] = None,
        status: str = "ready",
        limited_at: Optional[float] = None,
        cooldown_until: Optional[float] = None,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        last_used_at: Optional[float] = None,
        label: str = "",
    ):
        self.id = account_id
        self.profile_dir = profile_dir
        self.authuser = authuser
        self.status = status
        self.limited_at = limited_at
        self.cooldown_until = cooldown_until
        self.cooldown_seconds = cooldown_seconds
        self.last_used_at = last_used_at
        self.label = label or (f"authuser={authuser}" if authuser is not None else os.path.basename(profile_dir))

    def is_available(self, now: Optional[float] = None) -> bool:
        if now is None:
            now = time.time()
        if self.status != "rate_limited":
            return True
        if self.cooldown_until and now >= self.cooldown_until:
            self.status = "ready"
            self.limited_at = None
            self.cooldown_until = None
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "profile_dir": self.profile_dir,
            "authuser": self.authuser,
            "status": self.status,
            "limited_at": self.limited_at,
            "cooldown_until": self.cooldown_until,
            "cooldown_seconds": self.cooldown_seconds,
            "last_used_at": self.last_used_at,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        return cls(
            account_id=data["id"],
            profile_dir=data.get("profile_dir", ""),
            authuser=data.get("authuser"),
            status=data.get("status", "ready"),
            limited_at=data.get("limited_at"),
            cooldown_until=data.get("cooldown_until"),
            cooldown_seconds=data.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS),
            last_used_at=data.get("last_used_at"),
            label=data.get("label", ""),
        )


class AccountManager:
    """Manages rotation, cooldown timers, and active selection across multiple accounts."""

    def __init__(
        self,
        state_path: str,
        default_profile_dir: str,
        target_base_url: str = "https://aistudio.google.com/prompts/new_chat",
        profiles_list: Optional[List[str]] = None,
        authuser_count: int = 1,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ):
        self.state_path = state_path
        self.default_profile_dir = default_profile_dir
        self.target_base_url = target_base_url
        self.cooldown_seconds = cooldown_seconds
        self.authuser_count = authuser_count
        self.accounts: Dict[str, Account] = {}
        self.active_id: str = ""

        self._init_accounts(profiles_list, authuser_count)
        self._load_state()
        self._select_startup_account()

    def _init_accounts(self, profiles_list: Optional[List[str]], authuser_count: int):
        self.accounts.clear()

        # Mode A: If multiple distinct profile directories were provided
        if profiles_list and len(profiles_list) > 1:
            for i, p in enumerate(profiles_list):
                acc_id = f"profile_{i}"
                self.accounts[acc_id] = Account(
                    account_id=acc_id,
                    profile_dir=p,
                    authuser=None,
                    cooldown_seconds=self.cooldown_seconds,
                    label=os.path.basename(p) or f"profile_{i}",
                )
        else:
            # Mode B: Single profile with N logged-in accounts via ?authuser=0, 1, ...
            count = max(1, authuser_count)
            for i in range(count):
                acc_id = f"authuser_{i}"
                self.accounts[acc_id] = Account(
                    account_id=acc_id,
                    profile_dir=self.default_profile_dir,
                    authuser=i,
                    cooldown_seconds=self.cooldown_seconds,
                    label=f"authuser={i}",
                )

        if not self.active_id and self.accounts:
            self.active_id = next(iter(self.accounts.keys()))

    def _load_state(self):
        """Restore cooldown and status from runtime JSON file."""
        if not os.path.isfile(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            saved_accounts = data.get("accounts", {})
            now = time.time()
            for acc_id, acc_data in saved_accounts.items():
                if acc_id in self.accounts:
                    acc = self.accounts[acc_id]
                    acc.status = acc_data.get("status", "ready")
                    acc.limited_at = acc_data.get("limited_at")
                    acc.cooldown_until = acc_data.get("cooldown_until")
                    acc.last_used_at = acc_data.get("last_used_at")
                    # Auto-check if cooldown already expired while server was offline
                    acc.is_available(now)
            saved_active = data.get("active_id")
            if saved_active in self.accounts:
                self.active_id = saved_active
        except Exception as e:
            logger.warning(f"Could not load accounts state: {e}")

    def _save_state(self):
        """Persist state to runtime JSON."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
            payload = {
                "active_id": self.active_id,
                "accounts": {k: v.to_dict() for k, v in self.accounts.items()},
                "updated_at": time.time(),
            }
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, self.state_path)
        except Exception as e:
            logger.warning(f"Could not save accounts state: {e}")

    def _select_startup_account(self):
        """Pre-flight check: Ensure the chosen active account is not rate-limited."""
        now = time.time()
        active = self.accounts.get(self.active_id)
        if active and active.is_available(now):
            return

        # Current active is not available; find the first ready account
        for acc in self.accounts.values():
            if acc.is_available(now):
                self.active_id = acc.id
                logger.info(f"Startup pre-flight selected available account: {acc.id} ({acc.label})")
                self._save_state()
                return

        # If all accounts are rate-limited, keep the one with earliest cooldown expiry
        earliest = min(self.accounts.values(), key=lambda a: a.cooldown_until or float("inf"), default=None)
        if earliest:
            self.active_id = earliest.id
            logger.warning(
                f"All accounts are currently in cooldown! Earliest reset: {earliest.id} "
                f"in {max(0, int((earliest.cooldown_until or now) - now))}s."
            )

    def get_active_account(self) -> Account:
        if self.active_id not in self.accounts:
            self.active_id = next(iter(self.accounts.keys()))
        return self.accounts[self.active_id]

    def get_target_url(self, account: Optional[Account] = None) -> str:
        acc = account or self.get_active_account()
        if acc.authuser is None or acc.authuser == 0:
            return self.target_base_url
        sep = "&" if "?" in self.target_base_url else "?"
        return f"{self.target_base_url}{sep}authuser={acc.authuser}"
        return self.target_base_url

    def mark_rate_limited(self, account_id: Optional[str] = None, reason: str = "quota_exceeded", cooldown_seconds: Optional[float] = None) -> Account:
        target_id = account_id or self.active_id
        acc = self.accounts.get(target_id)
        if not acc:
            raise KeyError(f"Unknown account: {target_id}")

        now = time.time()
        duration = cooldown_seconds if cooldown_seconds is not None else acc.cooldown_seconds
        acc.status = "rate_limited"
        acc.limited_at = now
        acc.cooldown_until = now + duration
        logger.warning(
            f"Account {acc.id} ({acc.label}) marked as RATE_LIMITED (reason: {reason}). "
            f"Cooldown for {duration / 3600:.1f} hours until {time.ctime(acc.cooldown_until)}."
        )
        self._save_state()
        return acc

    def rotate_to_next(self, reason: str = "quota_exceeded") -> Optional[Account]:
        """Mark current as rate-limited and rotate to the next available account."""
        now = time.time()
        curr = self.get_active_account()
        if curr.status != "rate_limited":
            self.mark_rate_limited(curr.id, reason=reason)

        keys = list(self.accounts.keys())
        if len(keys) <= 1:
            if getattr(self, "authuser_count", 1) > 1 and curr.authuser == 0:
                candidate_id = "authuser_1"
                candidate = Account(
                    account_id=candidate_id,
                    profile_dir=curr.profile_dir,
                    authuser=1,
                    cooldown_seconds=self.cooldown_seconds,
                    label="authuser=1",
                )
                self.accounts[candidate_id] = candidate
                self.active_id = candidate.id
                candidate.last_used_at = now
                logger.info(f"Auto-expanded and rotated to dynamic account {candidate.id} ({candidate.label})")
                self._save_state()
                return candidate
            return None

        curr_idx = keys.index(curr.id)
        # Search starting from next account index
        for offset in range(1, len(keys)):
            candidate_id = keys[(curr_idx + offset) % len(keys)]
            candidate = self.accounts[candidate_id]
            if candidate.is_available(now):
                self.active_id = candidate.id
                candidate.last_used_at = now
                logger.info(f"Rotated active account from {curr.id} to {candidate.id} ({candidate.label})")
                self._save_state()
                return candidate

        logger.warning("Quota rotation attempted, but ALL accounts are currently rate-limited.")
        return None

    def earliest_reset_seconds(self) -> float:
        now = time.time()
        resets = [
            (acc.cooldown_until - now)
            for acc in self.accounts.values()
            if acc.cooldown_until and acc.cooldown_until > now
        ]
        return max(0.0, min(resets)) if resets else 0.0

    def stats(self) -> dict:
        now = time.time()
        active = self.get_active_account()
        return {
            "total_accounts": len(self.accounts),
            "active_account_id": self.active_id,
            "active_authuser": active.authuser,
            "active_label": active.label,
            "active_target_url": self.get_target_url(active),
            "accounts": [
                {
                    "id": a.id,
                    "label": a.label,
                    "authuser": a.authuser,
                    "status": "ready" if a.is_available(now) else "rate_limited",
                    "cooldown_remaining_seconds": max(0, int((a.cooldown_until or now) - now)) if not a.is_available(now) else 0,
                    "limited_at": a.limited_at,
                    "last_used_at": a.last_used_at,
                }
                for a in self.accounts.values()
            ],
        }
