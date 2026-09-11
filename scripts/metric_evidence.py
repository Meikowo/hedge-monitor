"""Shared conservative evidence guards for extraction and comparison."""
from decimal import Decimal, InvalidOperation
import re


def is_authorization_peak(quote, value):
    """Reject cap amounts, not an actual peak followed by cap commentary.

    Only relax the cap guard when the selected number is explicitly actual in
    its own clause. Ambiguous/same-number cap and actual clauses stay rejected.
    Commas inside thousands-formatted numbers are not clause separators.
    """
    cap = r'不超过|不得超过|授权|额度上限|拟开展|拟使用'
    if not re.search(cap, quote or ''):
        return False
    try:
        target = Decimal(str(value))
    except InvalidOperation:
        return True
    clauses = re.split(r'[，；;。]|(?<!\d),|,(?!\d)', quote)
    selected = []
    for clause in clauses:
        numbers = re.findall(r'[-+]?\d[\d,]*(?:\.\d+)?', clause)
        if any(Decimal(n.replace(',', '')) == target for n in numbers):
            selected.append(clause)
    return not (selected and all(not re.search(cap, c) for c in selected)
                and any(re.search(r'实际|已发生|已占用', c) for c in selected))
