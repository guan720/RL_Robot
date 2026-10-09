"""Scalar schedule check, not a VLA/robot test and not model training.

Mirrors the fixed-point loop at UniSteer cd87d240, actor_supervision.py
lines 562-583 and the decoder schedule at its locked LeRobot c8ce413d,
modeling_pi05.py lines 751-779. Uses Python scalars only.
"""
import json

UNISTEER_SHA = "cd87d240f5ec646e7590476593c3e95eb765b473"
LEROBOT_SHA = "c8ce413d738da15a2eed2d0832315779ea28cbf9"


def decoder(z, velocity, steps=10):
    dt = -1.0 / steps
    x = z
    for step in range(steps):
        time = 1.0 + step * dt
        x = x + dt * velocity(x, time)
    return x


def published_inverse(action, velocity, steps=10, iterations=16):
    delta = 1.0 / steps
    x_next = action
    residuals = []
    for step in range(steps - 1, -1, -1):
        time = step / steps
        x = x_next
        for _ in range(iterations):
            x = x_next - delta * velocity(x, time)
        residuals.append(abs(x + delta * velocity(x, time) - x_next))
        x_next = x
    return x_next, max(residuals)


def schedule_consistent_inverse(action, velocity, steps=10, iterations=16):
    delta = 1.0 / steps
    x_next = action
    for step in range(steps - 1, -1, -1):
        # Reverse the actual decoder's final update first: t=1/steps.
        time = 1.0 - step / steps
        x = x_next
        for _ in range(iterations):
            x = x_next + delta * velocity(x, time)
        x_next = x
    return x_next


def main():
    cases = {
        "constant_nonzero_v=1": lambda x, t: 1.0,
        "time_dependent_v=t": lambda x, t: t,
        "state_dependent_v=x": lambda x, t: x,
    }
    rows = []
    for name, velocity in cases.items():
        target = 0.25
        z_bad, residual = published_inverse(target, velocity)
        z_good = schedule_consistent_inverse(target, velocity)
        bad_out = decoder(z_bad, velocity)
        good_out = decoder(z_good, velocity)
        rows.append({
            "case": name,
            "target_action": target,
            "published_inverse_noise": z_bad,
            "published_local_equation_max_residual": residual,
            "published_roundtrip_action": bad_out,
            "published_roundtrip_abs_error": abs(bad_out - target),
            "schedule_consistent_inverse_noise": z_good,
            "schedule_consistent_roundtrip_abs_error": abs(good_out - target),
        })
    print(json.dumps({
        "scope": "Scalar algebra only. No VLA weights, robot execution, installation, or training.",
        "unisteer_sha": UNISTEER_SHA,
        "lerobot_sha": LEROBOT_SHA,
        "forward_source": "https://github.com/huggingface/lerobot/blob/" + LEROBOT_SHA + "/src/lerobot/policies/pi05/modeling_pi05.py#L751-L779",
        "inverse_source": "https://github.com/microsoft/UniSteer/blob/" + UNISTEER_SHA + "/src/tool/unisteer_actor_supervision.py#L562-L583",
        "results": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
