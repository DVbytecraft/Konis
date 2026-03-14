import { test, expect, request as apiRequest } from "@playwright/test";

const ADMIN_USER = process.env.E2E_ADMIN_USER || "";
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || "";
const ALLOW_MUTATIONS = process.env.E2E_ALLOW_MUTATIONS === "1";

async function login(page, username: string, password: string) {
  await page.goto("/login");
  await page.fill("#username", username);
  await page.fill("#password", password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

test.describe("Admin critical checks", () => {
  test("health check returns ok", async ({ page }) => {
    test.skip(!ADMIN_USER || !ADMIN_PASS, "Missing E2E admin credentials");
    await login(page, ADMIN_USER, ADMIN_PASS);
    const storage = await page.context().storageState();
    const api = await apiRequest.newContext({
      baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
      storageState: storage,
    });
    const resp = await api.get("/api/health/check/");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.status).toBe("ok");
  });

  test("admin can create and delete user", async ({ page }) => {
    test.skip(!ALLOW_MUTATIONS, "E2E_ALLOW_MUTATIONS=1 required");
    test.skip(!ADMIN_USER || !ADMIN_PASS, "Missing E2E admin credentials");
    await login(page, ADMIN_USER, ADMIN_PASS);
    const storage = await page.context().storageState();
    const api = await apiRequest.newContext({
      baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
      storageState: storage,
    });
    const username = `e2e_user_${Date.now()}`;
    const payload = {
      username,
      password: "E2ePass123!",
      role: "comptable",
      first_name: "E2E",
      last_name: "Test",
      email: `${username}@example.com`,
      is_active: true,
    };
    const createResp = await api.post("/api/admin/users/", { data: payload });
    expect(createResp.status()).toBe(201);
    const created = await createResp.json();
    const deleteResp = await api.delete(`/api/admin/users/${created.id}/`);
    expect(deleteResp.status()).toBe(204);
  });
});
