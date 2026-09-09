"""Independent exact-value specification and bounded reproducible test corpus."""
import csv
import random
import re
from fractions import Fraction

SEED = 20260909
GENERATED = 160
LIMIT = Fraction('999999999.99')


def classify(text, digits):
    # Adapter framing is separate from arithmetic: 64 ASCII bytes, trim spaces.
    text = text.encode('ascii')[:64].decode('ascii').strip(' ')
    unsigned = text
    # Only one sign is removed (a second sign remains malformed).
    if text[:1] in '+-':
        unsigned = text[1:]
    if len(unsigned) < 4:
        return 'INVALID_INPUT', None
    if len(unsigned) - 3 > digits:
        return 'OVERFLOW', None
    if not re.fullmatch(r'[+-]?[0-9]+\.[0-9]{2}', text):
        return 'INVALID_INPUT', None
    return None, Fraction(text)


def oracle(args):
    if len(args) != 2:
        return dict(exit=2, stdout='ERROR\tINVALID_INPUT\n', stderr='')
    fields = [classify(args[0], 9), classify(args[1], 4)]
    errors = [error for error, _ in fields if error]
    if errors:
        error = 'OVERFLOW' if 'OVERFLOW' in errors else 'INVALID_INPUT'
        return dict(exit=3 if error == 'OVERFLOW' else 2,
                    stdout='ERROR\t' + error + '\n', stderr='')
    # Work in exact currency/rate units, not the Rust parser's scaled integers.
    amount = fields[0][1] * fields[1][1] / 1200
    cents = int(amount * 100)  # Fraction.__int__ truncates toward zero.
    if abs(Fraction(cents, 100)) > LIMIT:
        return dict(exit=3, stdout='ERROR\tOVERFLOW\n', stderr='')
    sign = '-' if cents < 0 else ''
    return dict(exit=0, stdout=f'OK\t{sign}{abs(cents)//100}.{abs(cents)%100:02}\n', stderr='')


def corpus(root):
    cases = []
    with (root / 'fixtures/cases.tsv').open() as stream:
        for row in csv.reader(stream, delimiter='\t'):
            if not row or row[0].startswith('#'):
                continue
            key, category, balance, rate, status, tag, value = row
            cases.append(dict(id=key, category=category, args=[balance, rate],
                              committed=dict(exit=int(status), stdout=tag+'\t'+value+'\n', stderr='')))
    explicit = [
        ('positive-half-cent', ['6.00', '1.00']),
        ('negative-half-cent', ['-6.00', '1.00']),
        ('above-half-cent', ['6.01', '1.00']),
        ('below-half-cent', ['5.99', '1.00']),
        ('negative-zero', ['-0.00', '9999.99']),
        ('max-rate', ['1.00', '9999.99']),
        ('min-rate', ['1.00', '-9999.99']),
        ('negative-result-overflow', ['-999999999.99', '9999.99']),
        ('invalid-overflow-reversed', ['1000000000.00', 'abc']),
        ('empty', ['', '1.00']), ('missing', []), ('extra', ['1.00','1.00','x']),
        ('tab', ['\t1.00', '1.00']), ('second-sign', ['+-1.00', '1.00']),
        ('long-malformed', ['xxxxxxxxxx.00', '1.00']),
        ('capture64', ['1.00'+' '*60+'discarded', '1.00']),
    ]
    cases.extend(dict(id=key, category='explicit', args=args) for key, args in explicit)
    rng = random.Random(SEED)
    for index in range(GENERATED):
        def decimal(maximum):
            value = rng.randint(-maximum, maximum)
            return ('-' if value < 0 else '')+f'{abs(value)//100}.{abs(value)%100:02}'
        cases.append(dict(id=f'seed-{SEED}-{index:03}', category='generated',
                          args=[decimal(99_999_999_999), decimal(999_999)]))
    return cases
