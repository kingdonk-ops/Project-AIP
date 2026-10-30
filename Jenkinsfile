// CI for Project AIP, mirroring .github/workflows/ci.yml by running the SAME
// Makefile gates (make check-py / check-ts / check-docs / check-boundaries /
// check-client) rather than duplicating the workflow YAML. Each gate runs as a
// parallel stage in its own container, so the whole run is as wide as the
// executors allow. Requires the Docker Pipeline plugin and a node with the
// Docker CLI + daemon access.
pipeline {
    agent none

    options {
        timestamps()
        timeout(time: 40, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '30'))
        disableConcurrentBuilds()      // per-branch; different branches/PRs still run concurrently
    }

    stages {
        stage('CI') {
            parallel {

                // ---- Python: ruff, ruff format, pyright, pytest, aip-db lint ----
                // (make check-py) against a pgvector/pg16 service, as the `python` job does.
                stage('Python') {
                    agent any
                    environment {
                        AIP_TEST_DATABASE_URL = 'postgresql://aip_test:aip_test@db:5432/aip_test'
                    }
                    steps {
                        script {
                            def net = "aip-ci-${env.BUILD_NUMBER}-${env.EXECUTOR_NUMBER}"
                            sh "docker network create ${net}"
                            def pg = docker.image('pgvector/pgvector:pg16').run(
                                "--network ${net} --network-alias db " +
                                "-e POSTGRES_USER=aip_test -e POSTGRES_PASSWORD=aip_test -e POSTGRES_DB=aip_test")
                            try {
                                docker.image('ghcr.io/astral-sh/uv:python3.12-bookworm').inside(
                                        "--network ${net} -u root -e AIP_TEST_DATABASE_URL " +
                                        "-e UV_CACHE_DIR=${env.WORKSPACE}/.uv-cache -e HOME=${env.WORKSPACE}") {
                                    sh 'apt-get update -qq && apt-get install -y -qq make git >/dev/null'
                                    sh 'uv sync --all-packages --frozen'
                                    sh '''
                                        for i in $(seq 1 30); do
                                            uv run python -c "import psycopg; psycopg.connect('postgresql://aip_test:aip_test@db:5432/aip_test')" 2>/dev/null && break
                                            echo "waiting for postgres ($i/30)"; sleep 2
                                        done
                                    '''
                                    sh 'make check-py'
                                }
                            } finally {
                                pg.stop()
                                sh "docker network rm ${net} || true"
                            }
                        }
                    }
                    post {
                        always { junit allowEmptyResults: true, testResults: '**/pytest-*.xml' }
                    }
                }

                // ---- TypeScript: lint, typecheck, build, test (make check-ts) ----
                stage('TypeScript') {
                    agent {
                        docker {
                            image 'node:22-bookworm'
                            args '-u root -e HOME=/tmp -e COREPACK_HOME=/tmp/corepack'
                        }
                    }
                    steps {
                        sh 'apt-get update -qq && apt-get install -y -qq make >/dev/null'
                        sh 'corepack enable && corepack prepare pnpm@10.28.0 --activate'
                        sh 'pnpm install --frozen-lockfile'
                        sh 'make check-ts'
                    }
                }

                // ---- Docs + import/layout boundaries (make check-docs / check-boundaries) ----
                stage('Docs & Boundaries') {
                    agent {
                        docker {
                            image 'ghcr.io/astral-sh/uv:python3.12-bookworm'
                            args '-u root -e UV_CACHE_DIR=/tmp/uv -e HOME=/tmp'
                        }
                    }
                    steps {
                        sh 'apt-get update -qq && apt-get install -y -qq make git >/dev/null'
                        sh 'uv sync --all-packages --frozen'
                        sh 'make check-docs'
                        sh 'make check-boundaries'
                    }
                }

                // ---- Generated API client drift (make check-client) ----
                stage('API client drift') {
                    agent {
                        docker {
                            image 'node:22-bookworm'
                            args '-u root -e HOME=/tmp -e COREPACK_HOME=/tmp/corepack'
                        }
                    }
                    steps {
                        sh 'apt-get update -qq && apt-get install -y -qq make git python3 >/dev/null'
                        // uv for export_openapi + pnpm for client generate (check_client_drift.sh).
                        sh 'curl -LsSf https://astral.sh/uv/install.sh | sh && . $HOME/.local/bin/env'
                        sh 'corepack enable && corepack prepare pnpm@10.28.0 --activate'
                        sh 'pnpm install --frozen-lockfile'
                        sh '. $HOME/.local/bin/env && uv sync --all-packages --frozen && make check-client'
                    }
                }
            }
        }
    }
}

// NOTE: the heavier GitHub jobs — e2e (Playwright/compose), sbom, strip-check
// (docker image builds) and the full db/compose stacks — are intentionally not
// ported in this first pass. They need compose + image builds on the node and
// are best added as their own stages once the core gates are green here.
