"""信任邊界測試用的 review 標的，測完隨 PR 一起關掉，不要 merge。

存在的理由只有一個：讓 diff 不是空的，04 才有東西可以送去 review。
順便看 locate.py 的定位層在真實 PR 上指不指得對。
"""


def pick_above(scores, cutoff=0.7):
    picked = []
    for i in range(len(scores) + 1):
        if scores[i] >= cutoff:
            picked.append(scores[i])
    return picked
