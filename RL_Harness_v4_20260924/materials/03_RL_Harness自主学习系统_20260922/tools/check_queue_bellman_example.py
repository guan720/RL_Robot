"""Small analytic example of the design, not a test of a robot or RL codebase."""
from functools import lru_cache
from pathlib import Path
import json

gamma = 0.9
actions = (-1, 1)

def outcomes(position, committed):
    # Old committed action is executed now; new action only chooses next queue.
    for probability, delta in ((0.8, committed), (0.2, -committed)):
        next_position = max(0, min(2, position + delta))
        terminal = next_position == 2
        reward = 1.0 if terminal else -0.01
        yield probability, next_position, reward, terminal

def policy(position, committed, remaining):
    return 1

@lru_cache(None)
def bellman(position, committed, requested, remaining):
    if remaining == 0:
        return 0.0
    value = 0.0
    for p, ns, reward, terminal in outcomes(position, committed):
        tail = 0.0 if terminal else bellman(ns, requested, policy(ns, requested, remaining-1), remaining-1)
        value += p * (reward + gamma * tail)
    return value

def enumerate_returns(position, committed, requested, remaining):
    # An explicit trajectory tree, evaluated independently of the Q cache.
    frontier = [(1.0, position, committed, requested, 0.0, 1.0)]
    total = 0.0
    for step in range(remaining):
        following = []
        for prob, s, old, new, accumulated, discount in frontier:
            for p, ns, reward, terminal in outcomes(s, old):
                subtotal = accumulated + discount * reward
                if terminal or step == remaining-1:
                    total += prob*p*subtotal
                else:
                    following.append((prob*p,ns,new,policy(ns,new,remaining-step-1),subtotal,discount*gamma))
        frontier = following
    return total

cases = []
for remaining in range(1,7):
    for position in (0,1):
        for committed in actions:
            for requested in actions:
                q = bellman(position,committed,requested,remaining)
                exact = enumerate_returns(position,committed,requested,remaining)
                cases.append({'state':[position,committed,remaining], 'request':requested,
                              'bellman':q, 'trajectory_expectation':exact, 'difference':abs(q-exact)})
result = {'scope':'finite analytic toy; does not validate robot, deep RL convergence, or Harness accuracy',
          'count':len(cases), 'max_difference':max(x['difference'] for x in cases),
          'future_selected_target_counterexample':{'true_value':0.5,'biased_mixture':0.5*1+0.5*0.5},
          'cases':cases}
root = Path(__file__).resolve().parents[1]
(root/'evidence'/'queue_bellman_example.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
assert result['max_difference'] < 1e-12
print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2))
