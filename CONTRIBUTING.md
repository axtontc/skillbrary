# Contributing to Skillbrary

First off, thank you for considering contributing to Skillbrary! 

Skillbrary is engineered for distributed multi-agent swarms, which means we hold our architectural standards to extreme, deterministic benchmarks. We value contributions that improve latency, security, and idempotency.

## 🧠 Architectural Philosophy

Before submitting a Pull Request, please ensure your code aligns with our core tenets:
1. **Idempotency is Mandatory:** All operations must be strictly idempotent. If a function is run twice with the same inputs, the system state must not corrupt or duplicate.
2. **No Direct State Mutation:** Direct master state mutation is forbidden. Agents and systems must submit Intents via the Write-Ahead Log (WAL).
3. **Hardware Budgets:** We enforce strict latency constraints:
   - WAL appends: `< 10ms`
   - Router IPC: `< 50ms`
   - AST parsing: `< 100ms`

## 🚀 Development Workflow

1. **Fork the Repository:** Create your own fork and clone it locally.
2. **Environment Setup:** We mandate the use of `uv` for dependency management.
   ```bash
   uv sync
   ```
3. **Branch Isolation:** Create a strictly isolated branch for your feature or fix.
   ```bash
   git checkout -b feature/ast-optimization
   ```

## 🧪 Testing Constraints

We do not accept PRs without accompanying tests. 
- All complex concurrency rules and parsing mathematics MUST be isolated and mathematically proven in the test suite.
- Run tests before committing:
  ```bash
  uv run pytest
  ```

## 📝 Pull Request Process

1. Ensure your code passes all linting and test suites.
2. Update the README.md with details of any major changes to the interface.
3. Submit the PR with a clear description of the problem solved and the latency/performance metrics of your implementation.
4. A maintainer will review your PR against the Swarm architectural standards.

Thank you for helping us build the future of deterministic agent execution!
