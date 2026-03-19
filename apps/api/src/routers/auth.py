import uuid

from fastapi import APIRouter

from dependencies import CurrentUserDep, DevBootstrapTokenDep, issue_dev_access_token
from models import APIResponse, AuthTokenResponse, CurrentUserResponse, DevAuthTokenRequest, Meta

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/dev-token", response_model=APIResponse)
async def create_dev_token(
    payload: DevAuthTokenRequest,
    x_dev_api_token: DevBootstrapTokenDep,
):
    token, expires_at, user = issue_dev_access_token(
        requested_role=payload.requested_role,
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        email=payload.email,
        x_dev_api_token=x_dev_api_token,
    )
    return APIResponse(
        success=True,
        data=AuthTokenResponse(
            access_token=token,
            expires_at=expires_at.isoformat(),
            user=CurrentUserResponse(
                user_id=user["user_id"],
                tenant_id=user["tenant_id"],
                role=user["role"],
                email=user["email"],
                token_id=user["token_id"],
            ),
        ),
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("/me", response_model=APIResponse)
async def get_me(current_user: CurrentUserDep):
    return APIResponse(
        success=True,
        data=CurrentUserResponse(
            user_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
            role=current_user["role"],
            email=current_user["email"],
            token_id=current_user["token_id"],
        ),
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )
