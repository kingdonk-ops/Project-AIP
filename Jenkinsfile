// CI for Project AIP on self-hosted Jenkins (jenkins.bytedock.io).
// Runs the same gates as .github/workflows/ci.yml, executed directly on the
// controller (toolchains preinstalled under /var/jenkins_home) against a
// managed pgvector Postgres — no Docker daemon required. The two long poles
// (backend + frontend) run as parallel tracks.
//
// Not ported here (need Docker/compose): e2e (Playwright), compose stack,
// sbom, strip-check image builds — those stay on GitHub Actions for now.
pipeline {
    agent none

    options {
        timestamps()
        timeout(time: 40, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '30'))
        disableConcurrentBuilds()
    }

    environment {
        PATH                  = "/var/jenkins_home/bin:/var/jenkins_home/tools/node/bin:${PATH}"
        HOME                  = "/var/jenkins_home"
        UV_CACHE_DIR          = "/var/jenkins_home/.cache/uv"
        AIP_TEST_DATABASE_URL = "postgresql://aip_test:aip_test@zaqzezfntsrp0e5lqvpx18mh:5432/aip_test"
    }

    stages {
        stage('CI') {
            parallel {

                // Python gates + docs + boundaries + client drift (uv/pnpm toolchain).
                stage('Backend & checks') {
                    agent any
                    steps {
                        sh 'uv --version && node --version && pnpm --version'
                        sh 'uv sync --all-packages --frozen'
                        sh 'pnpm install --frozen-lockfile'

                        // make check-py
                        sh 'uv run ruff check'
                        sh 'uv run ruff format --check'
                        sh 'uv run pyright'
                        sh 'uv run pytest --junitxml=pytest-report.xml'
                        sh 'uv run aip-db lint'

                        // make check-boundaries
                        sh 'uv run lint-imports --no-cache'
                        sh 'uv run python tools/ci/check_manifests.py'
                        sh 'uv run python tools/gen_permissions.py --check'
                        sh 'uv run python tools/ci/check_layout.py'

                        // make check-docs (stdlib scripts run under uv's Python)
                        sh 'uv run python tools/ci/check_adrs.py'
                        sh 'uv run python -m unittest tools/ci/test_check_adrs.py'
                        sh 'uv run python tools/ci/check_security_docs.py'
                        sh 'uv run python -m unittest tools/ci/test_check_security_docs.py'
                        sh 'uv run python tools/ci/check_generated_header.py'
                        sh 'uv run python -m unittest tools/ci/test_check_generated_header.py'
                        sh 'uv run python -m unittest tools/ci/tests/test_check_licences.py tools/ci/tests/test_sbom_fill_licences.py'
                        sh 'uv run python -m unittest tools/ci/tests/test_check_prod_strip.py tools/ci/tests/test_check_vuln_exceptions.py'
                        sh 'uv run python tools/ci/check_vuln_exceptions.py'
                        // lint-tasks
                        sh 'uv run python tools/next_task.py --check'
                        sh 'uv run python tools/lint_tasks.py --quiet'

                        // make check-client (needs uv + pnpm; fails on drift under packages/api-client)
                        sh 'bash tools/ci/check_client_drift.sh'
                    }
                    post {
                        always { junit allowEmptyResults: true, testResults: 'pytest-report.xml' }
                    }
                }

                // TypeScript: lint, typecheck, build, test (make check-ts).
                stage('Frontend') {
                    agent any
                    steps {
                        sh 'node --version && pnpm --version'
                        sh 'pnpm install --frozen-lockfile'
                        sh 'pnpm -r lint'
                        sh 'pnpm -r typecheck'
                        sh 'pnpm -r build'
                        sh 'pnpm -r test'
                    }
                }
            }
        }
    }
}
