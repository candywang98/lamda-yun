import uvicorn

if __name__ == "__main__":
    # 18000 avoids the local Spider_XHS process that already binds :8000.
    uvicorn.run(
        "cloudctl_api.app:app",
        host="0.0.0.0",  # noqa: S104 - required for companion/edge access
        port=18000,
        reload=False,
    )
