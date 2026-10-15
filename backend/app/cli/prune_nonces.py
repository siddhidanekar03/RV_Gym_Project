import sys
import argparse
import logging
from typing import Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.core.database import SessionLocal, engine
from backend.app.models.attendance import ConsumedQRToken
from backend.app.services.attendance_service import purge_expired_qr_tokens

logger = logging.getLogger("rvfitness.cli.prune_nonces")

RVF_QR_CLEANUP_ADVISORY_LOCK_ID = 84729103


def run_prune_nonces(
    db: Session,
    dry_run: bool = False,
    lock_id: int = RVF_QR_CLEANUP_ADVISORY_LOCK_ID,
) -> Tuple[bool, int]:
    """
    Executes one-shot scheduled pruning of expired QR token nonces.
    Guarantees concurrency safety using PostgreSQL advisory locks.
    If another worker is currently running, exits cleanly without contention.
    """
    dialect_name = db.bind.dialect.name if db.bind else "sqlite"
    lock_acquired = False

    try:
        # 1. Acquire advisory lock on PostgreSQL to prevent concurrent runs across cron pods/workers
        if dialect_name == "postgresql":
            result = db.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": lock_id},
            ).scalar()
            if not result:
                logger.info(
                    f"Advisory lock {lock_id} is held by another running process. Exiting cleanly."
                )
                return False, 0
            lock_acquired = True

        # 2. Prune or inspect expired nonces
        now = datetime.now(timezone.utc)
        if dry_run:
            count = (
                db.query(ConsumedQRToken)
                .filter(ConsumedQRToken.expires_at < now)
                .count()
            )
            logger.info(f"[Dry Run] Found {count} expired QR nonces eligible for pruning.")
            return True, count

        count = purge_expired_qr_tokens(db)
        logger.info(f"Successfully pruned {count} expired QR nonces from database.")
        return True, count

    finally:
        # 3. Always release advisory lock on PostgreSQL
        if lock_acquired and dialect_name == "postgresql":
            try:
                db.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": lock_id},
                )
            except Exception as e:
                logger.error(f"Failed to release advisory lock {lock_id}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-shot scheduled cleanup of expired QR check-in nonces."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate cleanup and report count of eligible nonces without deleting.",
    )
    parser.add_argument(
        "--lock-id",
        type=int,
        default=RVF_QR_CLEANUP_ADVISORY_LOCK_ID,
        help="PostgreSQL advisory lock integer ID (default: 84729103).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    db = SessionLocal()
    try:
        success, count = run_prune_nonces(db=db, dry_run=args.dry_run, lock_id=args.lock_id)
        if not success:
            sys.exit(0)
        print(f"DONE: pruned {count} nonces (dry_run={args.dry_run})")
    except Exception as exc:
        logger.exception(f"Unhandled error during QR nonce pruning: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
