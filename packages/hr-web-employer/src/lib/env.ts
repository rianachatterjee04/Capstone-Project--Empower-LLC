// Note: use a truthy check (not ??) so an empty NEXT_PUBLIC_API_BASE_URL falls
// back instead of producing same-origin calls that the fintrahub.com proxy
// would misroute. Production points straight at the People/HR backend.
const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
export const env = {
  apiBaseUrl:
    configuredApiBase && configuredApiBase.trim() !== ""
      ? configuredApiBase
      : process.env.NODE_ENV === "production"
        ? "https://fintra-hr-api.onrender.com/api"
        : "http://localhost:8000/api",
};
