import { test, expect } from "@playwright/test";

const ADMIN_USER = process.env.E2E_ADMIN_USER || "";
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || "";
const COMPTABLE_USER = process.env.E2E_COMPTABLE_USER || "";
const COMPTABLE_PASS = process.env.E2E_COMPTABLE_PASS || "";
const USINE_USER = process.env.E2E_USINE_USER || "";
const USINE_PASS = process.env.E2E_USINE_PASS || "";
const BOUTIQUE_USER = process.env.E2E_BOUTIQUE_USER || "";
const BOUTIQUE_PASS = process.env.E2E_BOUTIQUE_PASS || "";

async function login(page, username: string, password: string) {
  await page.goto("/login");
  await page.fill("#username", username);
  await page.fill("#password", password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

const rolePaths = {
  admin: [
    "/admin",
    "/admin/users",
    "/admin/factories",
    "/admin/magasins",
    "/admin/produits",
    "/admin/rapport",
    "/factures",
    "/comptable",
    "/comptable/depenses",
  ],
  comptable: [
    "/comptable",
    "/comptable/depenses",
    "/factures",
  ],
  usine: [
    "/factory",
    "/factory/raw-materials",
    "/factory/production",
    "/factory/transfers",
    "/factory/shop-stock",
    "/factory/mouture",
    "/factures",
  ],
  boutique: [
    "/boutique/caisse",
    "/boutique/mouture",
    "/boutique/tickets",
    "/factures",
  ],
};

test.describe("Role interface smoke", () => {
  test("admin interfaces", async ({ page }) => {
    test.skip(!ADMIN_USER || !ADMIN_PASS, "Missing E2E admin credentials");
    await login(page, ADMIN_USER, ADMIN_PASS);
    for (const path of rolePaths.admin) {
      await page.goto(path);
      await expect(page.getByText("KONIS")).toBeVisible();
      await expect(page).toHaveURL(new RegExp(path.replace("/", "\\/")));
    }
  });

  test("comptable interfaces", async ({ page }) => {
    test.skip(!COMPTABLE_USER || !COMPTABLE_PASS, "Missing E2E comptable credentials");
    await login(page, COMPTABLE_USER, COMPTABLE_PASS);
    for (const path of rolePaths.comptable) {
      await page.goto(path);
      await expect(page.getByText("KONIS")).toBeVisible();
      await expect(page).toHaveURL(new RegExp(path.replace("/", "\\/")));
    }
  });

  test("usine interfaces", async ({ page }) => {
    test.skip(!USINE_USER || !USINE_PASS, "Missing E2E usine credentials");
    await login(page, USINE_USER, USINE_PASS);
    for (const path of rolePaths.usine) {
      await page.goto(path);
      await expect(page.getByText("KONIS")).toBeVisible();
      await expect(page).toHaveURL(new RegExp(path.replace("/", "\\/")));
    }
  });

  test("boutique interfaces", async ({ page }) => {
    test.skip(!BOUTIQUE_USER || !BOUTIQUE_PASS, "Missing E2E boutique credentials");
    await login(page, BOUTIQUE_USER, BOUTIQUE_PASS);
    for (const path of rolePaths.boutique) {
      await page.goto(path);
      await expect(page.getByText("KONIS")).toBeVisible();
      await expect(page).toHaveURL(new RegExp(path.replace("/", "\\/")));
    }
  });
});
