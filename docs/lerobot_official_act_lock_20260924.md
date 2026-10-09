# Official LeRobot ACT migration lock

## Version check

PyPI currently exposes `lerobot 0.4.4` as the latest version. The wheel metadata requires `torch>=2.2.1,<2.11.0`, so the existing RL environment's `torch 2.4.1+cu124` is in range. It declares `torchvision>=0.21.0,<0.26.0`, while this environment has `torchvision 0.19.1+cu124`; therefore the current environment is not a clean supported official runtime.

The official entry points inspected from the `lerobot==0.4.4` wheel are:

- `lerobot.policies.act.configuration_act.ACTConfig`
- `lerobot.policies.act.modeling_act.ACTPolicy`
- `chunk_size` for predicted action chunk length
- `n_action_steps` for receding-horizon execution
- `temporal_ensemble_coeff` for temporal aggregation

The wheel was probed in an isolated target directory under `runs/infra/lerobot_act_lift_state_overfit/official_probe/`; the existing RL environment was not overwritten. Import probing stops on additional transitive dependencies (`mypy_extensions` and further package requirements), so no official model training was started and no official ACT checkpoint is claimed.

## Dataset status

The existing export at `runs/infra/lerobot_act_lift_state_overfit/` already preserves the requested split and semantics:

- train `1000–1023`, validation `2000–2007`, test `5000–5019`;
- 20 Hz, state/proprio observation, 7D OSC_POSE action;
- `+1` gripper close and `-1` gripper open;
- K=4 chunk targets, original train mean/std, pinned object seed `20260923` and geometry;
- episode boundaries and timestamps in `meta/episodes.jsonl` and per-episode data files.

The data is a LeRobot-compatible interchange export. It has not been wrapped in the official `LeRobotDataset` class because the official runtime dependency set is not currently satisfied.

## Acceptance status

- Teacher data export: passed.
- Single episode teacher action alignment: passed with maximum error `0.0`.
- 20-episode teacher replay truth check: passed `20/20` `success_grasp_verified`.
- Official LeRobot ACT single-episode learned overfit: **not run**; blocked by the incompatible/missing official runtime dependencies above.
- Full official ACT training: not started.
- 20-episode learned ACT extension: not started.

The existing teacher replay result must remain labeled teacher replay and must not be reported as learned ACT. Before official overfit, create an isolated environment locking `lerobot==0.4.4`, a compatible `torchvision` release, and all wheel dependencies; then instantiate `ACTConfig` with state input, `chunk_size=4`, `n_action_steps=4`, and `temporal_ensemble_coeff=None`.
