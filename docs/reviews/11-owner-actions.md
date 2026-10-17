# Review 11: owner actions

These are the steps from the [2026-10-16 gap review](11-codebase-gap-review-2026-10-16.md) that only
the repository owner can take. Each one needs access to Coolify or the GitHub repository settings,
which agents do not have. Work through them in order: step 2 changes the passwords that step 3
stores.

| # | Action | Where | Closes |
|---|---|---|---|
| 1 | Lock down the mock IdP's self-service in the running demo | Coolify, keycloak container terminal | H1 (the part PR #101 cannot reach) |
| 2 | Change the demo users' passwords | Coolify, keycloak container terminal | H1 stopgap, until SECURITY-11 |
| 3 | Add the demo e2e secrets and make the skeleton check required | GitHub settings | O1 |
| 4 | Add the image-signing key | GitHub settings | O2 |
| 5 | Later: run the release path once | GitHub (tag push) | M15, after its glob fix |

## Why the demo needs hand changes

The demo Keycloak starts with `--import-realm`, which **skips realms that already exist**. Realm
changes merged to `main` (such as PR #101's) therefore reach new installs and CI, but not the
running demo. Steps 1 and 2 apply them by hand. Both survive redeploys for the same reason. They
are lost only if the Keycloak database is reset, and then step 1 is no longer needed (the fresh
import already has it) but step 2 must be repeated.

## 1. Lock down the mock IdP's self-service

**Why:** the brokers trust the mock IdP's emails. A mock IdP user who could change their own email
could sign in to the app as someone else. With the public passwords, anyone could also lock alice or
bob out by changing their password or adding OTP.

In Coolify, open the demo application, then **Terminal**, and choose the **keycloak** container. Run:

```sh
K=/opt/keycloak/bin/kcadm.sh
$K config credentials --server http://localhost:8080/auth --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"
for a in UPDATE_PROFILE UPDATE_EMAIL VERIFY_PROFILE UPDATE_PASSWORD CONFIGURE_TOTP; do $K update authentication/required-actions/$a -r mock-idp -s enabled=false; done
cat > /tmp/up.json <<'JSON'
{"attributes": [{"name": "username", "displayName": "${username}", "validations": {"length": {"min": 3, "max": 255}, "username-prohibited-characters": {}, "up-username-not-idn-homograph": {}}, "permissions": {"view": ["admin", "user"], "edit": ["admin"]}, "multivalued": false}, {"name": "email", "displayName": "${email}", "validations": {"email": {}, "length": {"max": 255}}, "permissions": {"view": ["admin", "user"], "edit": ["admin"]}, "multivalued": false}, {"name": "firstName", "displayName": "${firstName}", "validations": {"length": {"max": 255}, "person-name-prohibited-characters": {}}, "permissions": {"view": ["admin", "user"], "edit": ["admin"]}, "multivalued": false}, {"name": "lastName", "displayName": "${lastName}", "validations": {"length": {"max": 255}, "person-name-prohibited-characters": {}}, "permissions": {"view": ["admin", "user"], "edit": ["admin"]}, "multivalued": false}], "groups": [{"name": "user-metadata", "displayHeader": "User metadata", "displayDescription": "Attributes, which refer to user metadata"}]}
JSON
$K update users/profile -r mock-idp -f /tmp/up.json
$K get users/profile -r mock-idp
```

**Check:**
- The last command prints the profile. `username`, `email`, `firstName` and `lastName` should each
  show only `admin` under `edit`.
- `UPDATE_EMAIL` may say "not found" when that Keycloak feature is off. That is fine.
- If you have replaced the bootstrap admin, sign in with your own admin user in the second line instead.

Keep this terminal open for step 2.

## 2. Change the demo users' passwords

**Why:** alice (`alice@kaefer.test`) and bob (`bob@acme.test`) are tenant admins of the two demo
tenants. Their passwords are committed in `infra/keycloak/realm-mock-idp.json` in this public
repository, so anyone can sign in to the demo as them. The real fix (SECURITY-11) takes the demo
users from secrets. Until it lands, give the running demo new passwords.

Make two new long random passwords in your password manager, then in the same terminal run:

```sh
$K set-password -r mock-idp --username alice@kaefer.test
$K set-password -r mock-idp --username bob@acme.test
```

Each command asks for the new password, so it does not end up in the shell history.

**Check:** in a private browser window, sign in to the demo as alice with the **old** password
(`alice_dev_only_password`). It should be refused. The new password should work.

**Alternative:** you can put basic auth or an IP allow-list in front of the whole demo instead, in
Coolify or at your DNS/proxy. That also hides the demo from everyone else. But the deploy check in
step 3 cannot get through basic auth, and an IP allow-list must include GitHub's runners. Changing
the passwords is the simpler stopgap.

## 3. Demo e2e secrets and the required check (O1)

**Why:** after every deploy, `deploy-coolify.yml` signs in to the demo as alice and bob. Without
these secrets it skips that step and still passes, so a broken demo deploy looks green.

In GitHub, open **Settings → Environments → `coolify-demo` → Environment secrets** and add:

| Secret | Value |
|---|---|
| `E2E_USER_A` | `alice@kaefer.test` |
| `E2E_PASS_A` | alice's new password from step 2 |
| `E2E_USER_B` | `bob@acme.test` |
| `E2E_PASS_B` | bob's new password from step 2 |

These go on the **`coolify-demo` environment**, not the repository, because that is where the
deploy job reads them.

Then make the skeleton check required. Open **Settings → Branches** (or **Rules → Rulesets**) and
edit the rule for `main`. Under the required status checks, add
**E2E walking skeleton (compose, real sign-in, two tenants)**.

**Check:** on the next push to `main`, the deploy run's step "Walking skeleton against the demo"
should run Playwright and pass. It should not show the notice "E2E_USER_A/B secrets are not set".

## 4. Image-signing key (O2)

**Why:** `security.yml` signs the image digests and SBOMs. Without a key it signs with a throwaway
key on every run and warns "COSIGN_PRIVATE_KEY is not set". Those signatures prove nothing.

On a machine with Docker, in an empty folder:

```sh
docker run --rm -it -v "$PWD:/keys" -w /keys ghcr.io/sigstore/cosign/cosign:v3.1.1 generate-key-pair
```

It asks for a password and writes `cosign.key` (private) and `cosign.pub` (public).

In GitHub, open **Settings → Secrets and variables → Actions → Repository secrets** and add:

| Secret | Value |
|---|---|
| `COSIGN_PRIVATE_KEY` | the full contents of `cosign.key` |
| `COSIGN_PASSWORD` | the password you just chose |

Keep `cosign.key` and the password in your password manager, then delete the local `cosign.key`.
`cosign.pub` is public and can be shared with anyone who verifies the images.

**Check:** the next `security` workflow run no longer warns about an ephemeral key, and its
evidence includes `cosign.pub` instead of `cosign.ephemeral.pub`.

## 5. Later: run the release path once (M15)

The release workflow has never run, and its sandbox-image glob is wrong (see M15). After a PR fixes
the glob, push a throwaway tag once to prove the SBOM and licence path end to end:

```sh
git tag v0.0.0-sbomtest origin/main
git push origin v0.0.0-sbomtest
```

Delete the tag and its draft release afterwards if you don't want to keep them.

## Not covered here

- **Your laptop's WSL disk:** `ext4.vhdx` is still about 35 GB after the cleanup on 2026-10-16. To give
  the space back to C:, run `wsl --shutdown`, then in an administrator prompt run `diskpart`,
  `select vdisk file="<path to ext4.vhdx>"`, `attach vdisk readonly`, `compact vdisk`,
  `detach vdisk`. If you can't get admin rights, ask IT.
- **The code findings** (SECURITY-11 to 15, OPS-17, TESTING-12 and the rest) are on the board.
  Agents pick them up through `tools/next_task.py`.
