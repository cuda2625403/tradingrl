import numpy as np

sl = 40

# 単一のアクションを選択し続けることにペナルティーをかけ抑制する
def reward(trend, pip, action, position, states, pip_cost, spread, extend, total_pip, penalty):
    if action == 0:
        if position == 2:
            p = [s - trend for s in states]
            extend(p)
            total_pip = sum(pip)
            states = [trend + spread]
            penalty = 0
            position = 1
        else:
            states.append(trend + spread)
            total_pip -= (penalty * 10/ pip_cost)
            penalty += 1
            position = 1
    elif action == 1:
        if position == 1:
            p = [trend - s for s in states]
            extend(p)
            total_pip = sum(pip)
            states = [trend - spread]
            penalty = 0
            position = 2
        else:
            states.append(trend - spread)
            total_pip -= (penalty * 10/ pip_cost)
            penalty += 1
            position = 2
    elif action == 2:
        if position == 3:
            total_pip -= (penalty * 20 / pip_cost)
            penalty += 1
        else:
            penalty = 0
        position =3 

    return states, pip, position, total_pip, penalty


# def reward(trend,pip,action,position,states,pip_cost,spread,extend,total_pip):
#     if action == 0:
#         if position == 2:
#             p = [s - trend for s in states]
#             extend(p)
#             total_pip = sum(pip)
#             states = [trend + spread]
#             position = 1
#         else:
#             states.append(trend + spread)
#             position = 1
#     elif action == 1:
#         if position == 1:
#             p = [trend - s for s in states]
#             extend(p)
#             total_pip = sum(pip)
#             states = [trend - spread]
#             position = 2
#         else:
#             states.append(trend - spread)
#             position = 2

#     return states,pip,position,total_pip


def reward2(trend,pip,action,position,states,pip_cost,spread,extend,total_pip):
    if action == 0:
        if position == 2:
            p = [s - trend for s in states]
            extend(p)
            total_pip = sum(pip)
            states = [trend + spread]
            position = 1
        else:
            states.append(trend + spread)
            position = 1
    elif action == 1:
        if position == 1:
            p = [trend - s for s in states]
            extend(p)
            total_pip = sum(pip)
            states = [trend - spread]
            position = 2
        else:
            states.append(trend - spread)
            position = 2

    return states,pip,position,total_pip

def reward3(trend,pip,action,position,states,pip_cost,spread,extend,total_pip):
    if action == 0:
        if position == 2:
            p = states - trend
            extend(p)
            total_pip = sum(pip)
            states = trend + spread
            position = 1
    elif action == 1:
        if position == 1:
            p = trend - states
            extend(p)
            total_pip = sum(pip)
            states = trend - spread
            position = 2

    return states,pip,position,total_pip


def reward4( trend, pip, action, position, states, pip_cost, spread):
    if action == 0:
        if position == 3:
            states = [trend + spread]
            position = 1
        elif position == 1:
          sub = 0
          p = [(trend - s) * pip_cost for s in states]
          for b in range(0,len(p)):
            l = 0 if p[b] <= -40 else 1
            if l == 0:
              pip.append(-40)
              states.pop(b-sub)
              sub += 1
            states.append(trend + spread)
            position = 1
        elif position == 2:
          p = [(s - trend) * pip_cost for s in states]
          for b in p:
            b = -40.0 if b <= -40 else b
            pip.append(b)
          states = [trend + spread]
          position = 1
    elif action == 1:
        if position == 3:
            states = [trend - spread]
            position = 2
        elif position == 2:
          sub = 0
          p = [(s - trend) * pip_cost for s in states]
          for b in range(0,len(p)):
            l = 0 if p[b] <= -40 else 1
            if l == 0:
              pip.append(-40)
              states.pop(b-sub)
              sub += 1
          states.append(trend - spread)
          position = 2
        elif position == 1:
            p = [(trend - s) * pip_cost for s in states]
            for b in p:
                b = -40.0 if b <= -40 else b
                pip.append(b)
            states = [trend + spread]
            position = 2
    return states,pip,position
