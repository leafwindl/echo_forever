import hashlib
import hmac
import math
from datetime import UTC, datetime

from db.postgres_connection import transaction

from features.auth.domain.entities import AuthenticatedSession, AuthError
from features.auth.domain.services import AuthRepository, SessionTokenIssuer


def _phone_user_id(phone: str) -> str:
    digest = hashlib.sha256(phone.encode()).hexdigest()[:24]
    return f"phone_{digest}"


class PostgresAuthRepository(AuthRepository):
    def create_challenge(
        self,
        *,
        request_id: str,
        phone: str,
        code_hash: str,
        purpose: str,
        device_id: str,
        expires_in: int,
        resend_after: int,
    ) -> None:
        retry_after: int | None = None
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (phone,))
            cursor.execute(
                """
                SELECT created_at
                FROM sms_verification_challenges
                WHERE phone = %s AND consumed_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (phone,),
            )
            previous = cursor.fetchone()
            if previous:
                created_at = previous["created_at"]
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                elapsed = (datetime.now(UTC) - created_at).total_seconds()
                if elapsed < resend_after:
                    retry_after = max(1, math.ceil(resend_after - elapsed))

            if retry_after is None:
                cursor.execute(
                    """
                    INSERT INTO sms_verification_challenges (
                        request_id, phone, code_hash, purpose, device_id, attempts, expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 0, NOW() + (%s * INTERVAL '1 second'))
                    """,
                    (request_id, phone, code_hash, purpose, device_id, expires_in),
                )

        if retry_after is not None:
            raise AuthError(
                "AUTH_SMS_RATE_LIMITED",
                "验证码发送过于频繁，请稍后再试",
                retry_after=retry_after,
            )

    def invalidate_challenge(self, request_id: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE sms_verification_challenges
                SET consumed_at = COALESCE(consumed_at, NOW()), updated_at = NOW()
                WHERE request_id = %s
                """,
                (request_id,),
            )

    def verify_challenge_and_create_session(
        self,
        *,
        request_id: str,
        phone: str,
        code_hash: str,
        device_id: str,
        maximum_attempts: int,
        access_expires_in: int,
        refresh_expires_in: int,
        onboarding_completed: bool,
        token_issuer: SessionTokenIssuer,
    ) -> AuthenticatedSession:
        failure: AuthError | None = None
        session: AuthenticatedSession | None = None

        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT request_id, phone, code_hash, purpose, device_id, attempts,
                       expires_at, consumed_at
                FROM sms_verification_challenges
                WHERE request_id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            challenge = cursor.fetchone()
            if not challenge or challenge["phone"] != phone or challenge["device_id"] != device_id:
                failure = AuthError(
                    "AUTH_CHALLENGE_INVALID",
                    "验证码请求与手机号或设备不匹配",
                )
            elif challenge["purpose"] != "login":
                failure = AuthError("AUTH_CHALLENGE_INVALID", "验证码请求无效")
            elif challenge["consumed_at"] is not None:
                failure = AuthError("AUTH_CODE_EXPIRED", "验证码已过期或已使用")
            elif challenge["expires_at"] <= datetime.now(UTC):
                cursor.execute(
                    """
                    UPDATE sms_verification_challenges
                    SET consumed_at = NOW(), updated_at = NOW()
                    WHERE request_id = %s
                    """,
                    (request_id,),
                )
                failure = AuthError("AUTH_CODE_EXPIRED", "验证码已过期或已使用")
            elif int(challenge["attempts"]) >= maximum_attempts:
                cursor.execute(
                    """
                    UPDATE sms_verification_challenges
                    SET consumed_at = COALESCE(consumed_at, NOW()), updated_at = NOW()
                    WHERE request_id = %s
                    """,
                    (request_id,),
                )
                failure = AuthError("AUTH_CODE_ATTEMPTS_EXCEEDED", "验证码尝试次数已用尽")
            elif not hmac.compare_digest(str(challenge["code_hash"]), code_hash):
                attempts = int(challenge["attempts"]) + 1
                exhausted = attempts >= maximum_attempts
                cursor.execute(
                    """
                    UPDATE sms_verification_challenges
                    SET attempts = %s,
                        consumed_at = CASE WHEN %s THEN NOW() ELSE consumed_at END,
                        updated_at = NOW()
                    WHERE request_id = %s
                    """,
                    (attempts, exhausted, request_id),
                )
                if exhausted:
                    failure = AuthError(
                        "AUTH_CODE_ATTEMPTS_EXCEEDED",
                        "验证码尝试次数已用尽",
                    )
                else:
                    remaining = maximum_attempts - attempts
                    failure = AuthError(
                        "AUTH_CODE_INVALID",
                        f"验证码错误，还可尝试 {remaining} 次",
                    )
            else:
                session = self._create_phone_session(
                    cursor=cursor,
                    request_id=request_id,
                    phone=phone,
                    device_id=device_id,
                    access_expires_in=access_expires_in,
                    refresh_expires_in=refresh_expires_in,
                    onboarding_completed=onboarding_completed,
                    token_issuer=token_issuer,
                )

        if failure is not None:
            raise failure
        if session is None:
            raise RuntimeError("Authentication transaction produced no session")
        return session

    def _create_phone_session(
        self,
        *,
        cursor,
        request_id: str,
        phone: str,
        device_id: str,
        access_expires_in: int,
        refresh_expires_in: int,
        onboarding_completed: bool,
        token_issuer: SessionTokenIssuer,
    ) -> AuthenticatedSession:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (phone,))
        cursor.execute(
            "SELECT user_id, status FROM users WHERE phone = %s FOR UPDATE",
            (phone,),
        )
        user = cursor.fetchone()
        is_new_user = user is None
        if user is None:
            user_id = _phone_user_id(phone)
            cursor.execute(
                """
                INSERT INTO users (user_id, phone, phone_verified_at)
                VALUES (%s, %s, NOW())
                RETURNING user_id, status
                """,
                (user_id, phone),
            )
            user = cursor.fetchone()
            cursor.execute(
                """
                INSERT INTO user_personas (
                    user_id, is_customized, onboarding_completed, schema_version
                )
                VALUES (%s, FALSE, %s, 3)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id, onboarding_completed),
            )
            cursor.execute(
                """
                INSERT INTO relationship_states (user_id, schema_version)
                VALUES (%s, 1)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id,),
            )
        else:
            user_id = str(user["user_id"])
            cursor.execute(
                """
                UPDATE users SET phone_verified_at = COALESCE(phone_verified_at, NOW()),
                                 updated_at = NOW()
                WHERE user_id = %s
                """,
                (user_id,),
            )

        if not user or user["status"] != "active":
            raise AuthError("AUTH_USER_DISABLED", "账号当前不可用")

        refresh = token_issuer.new_refresh_token()
        access_token = token_issuer.issue_access_token(user_id)
        family_id = f"rtf_{hashlib.sha256(refresh.raw_token.encode()).hexdigest()[:32]}"
        cursor.execute(
            """
            INSERT INTO auth_refresh_tokens (
                token_id, token_hash, token_family_id, user_id, device_id, expires_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW() + (%s * INTERVAL '1 second'))
            """,
            (
                refresh.token_id,
                refresh.token_hash,
                family_id,
                user_id,
                device_id,
                refresh_expires_in,
            ),
        )
        cursor.execute(
            """
            UPDATE sms_verification_challenges
            SET consumed_at = NOW(), updated_at = NOW()
            WHERE request_id = %s
            """,
            (request_id,),
        )
        return AuthenticatedSession(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh.raw_token,
            expires_in=access_expires_in,
            refresh_expires_in=refresh_expires_in,
            is_new_user=is_new_user,
        )

    def rotate_refresh_token(
        self,
        *,
        token_hash: str,
        device_id: str,
        access_expires_in: int,
        refresh_expires_in: int,
        token_issuer: SessionTokenIssuer,
    ) -> AuthenticatedSession:
        failure: AuthError | None = None
        session: AuthenticatedSession | None = None

        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT token_id, token_family_id, user_id, device_id, expires_at,
                       used_at, revoked_at
                FROM auth_refresh_tokens
                WHERE token_hash = %s
                FOR UPDATE
                """,
                (token_hash,),
            )
            stored = cursor.fetchone()
            if not stored or stored["device_id"] != device_id:
                failure = AuthError("AUTH_REFRESH_INVALID", "刷新凭证无效")
            elif stored["used_at"] is not None:
                cursor.execute(
                    """
                    UPDATE auth_refresh_tokens
                    SET revoked_at = COALESCE(revoked_at, NOW()), updated_at = NOW()
                    WHERE token_family_id = %s
                    """,
                    (stored["token_family_id"],),
                )
                failure = AuthError("AUTH_REFRESH_REUSED", "检测到刷新凭证重放")
            elif stored["revoked_at"] is not None:
                failure = AuthError("AUTH_REFRESH_INVALID", "刷新凭证无效")
            elif stored["expires_at"] <= datetime.now(UTC):
                cursor.execute(
                    """
                    UPDATE auth_refresh_tokens
                    SET revoked_at = COALESCE(revoked_at, NOW()), updated_at = NOW()
                    WHERE token_id = %s
                    """,
                    (stored["token_id"],),
                )
                failure = AuthError("AUTH_REFRESH_EXPIRED", "刷新凭证已过期")
            else:
                cursor.execute(
                    "SELECT status FROM users WHERE user_id = %s",
                    (stored["user_id"],),
                )
                user = cursor.fetchone()
                if not user or user["status"] != "active":
                    failure = AuthError("AUTH_USER_DISABLED", "账号当前不可用")
                else:
                    refresh = token_issuer.new_refresh_token()
                    access_token = token_issuer.issue_access_token(str(stored["user_id"]))
                    cursor.execute(
                        """
                        INSERT INTO auth_refresh_tokens (
                            token_id, token_hash, token_family_id, user_id, device_id, expires_at
                        )
                        VALUES (%s, %s, %s, %s, %s, NOW() + (%s * INTERVAL '1 second'))
                        """,
                        (
                            refresh.token_id,
                            refresh.token_hash,
                            stored["token_family_id"],
                            stored["user_id"],
                            device_id,
                            refresh_expires_in,
                        ),
                    )
                    cursor.execute(
                        """
                        UPDATE auth_refresh_tokens
                        SET used_at = NOW(), replaced_by = %s, updated_at = NOW()
                        WHERE token_id = %s
                        """,
                        (refresh.token_id, stored["token_id"]),
                    )
                    session = AuthenticatedSession(
                        user_id=str(stored["user_id"]),
                        access_token=access_token,
                        refresh_token=refresh.raw_token,
                        expires_in=access_expires_in,
                        refresh_expires_in=refresh_expires_in,
                    )

        if failure is not None:
            raise failure
        if session is None:
            raise RuntimeError("Refresh transaction produced no session")
        return session

    def revoke_refresh_family(self, *, token_hash: str, user_id: str, device_id: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT token_family_id
                FROM auth_refresh_tokens
                WHERE token_hash = %s AND user_id = %s AND device_id = %s
                FOR UPDATE
                """,
                (token_hash, user_id, device_id),
            )
            stored = cursor.fetchone()
            if stored:
                cursor.execute(
                    """
                    UPDATE auth_refresh_tokens
                    SET revoked_at = COALESCE(revoked_at, NOW()), updated_at = NOW()
                    WHERE token_family_id = %s
                    """,
                    (stored["token_family_id"],),
                )

    def upsert_user(self, user_id: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (user_id)
                VALUES (%s)
                ON CONFLICT(user_id) DO UPDATE SET updated_at = NOW()
                """,
                (user_id,),
            )


_repository = PostgresAuthRepository()


def upsert_user(user_id: str, conn=None) -> None:
    """Compatibility boundary used by existing repositories when persisting user-owned data."""
    if conn is None:
        _repository.upsert_user(user_id)
        return
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO users (user_id)
            VALUES (%s)
            ON CONFLICT(user_id) DO UPDATE SET updated_at = NOW()
            """,
            (user_id,),
        )
