import sys
from fractions import Fraction
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from numeric import oracle, corpus

class NumericTests(unittest.TestCase):
    def test_hand_derived(self):
        for args,value in [(['100.00','12.00'],'1.00'),(['6.00','1.00'],'0.00'),
                           (['-6.00','1.00'],'0.00'),(['12.00','1.00'],'0.01'),
                           (['-12.00','1.00'],'-0.01'),(['999991666.73','1200.01'],'999999999.99')]:
            self.assertEqual(oracle(args),dict(exit=0,stdout='OK\t'+value+'\n',stderr=''))
        exact=Fraction('999991666.73')*Fraction('1200.01')/1200
        self.assertLess(Fraction('999999999.99'),exact)
        self.assertLess(exact,Fraction('1000000000.00'))

    def test_precedence_and_width(self):
        for args in [['abc','10000.00'],['1000000000.00','abc'],['xxxxxxxxxx.00','1.00']]:
            self.assertEqual(oracle(args)['exit'],3)
        for args in [[],['1.00'],['+-1.00','1.00'],['\t1.00','1.00']]:
            self.assertEqual(oracle(args)['exit'],2)

    def test_committed_expectations_and_reproducibility(self):
        root=Path(__file__).resolve().parents[1]
        first=corpus(root)
        self.assertEqual(first,corpus(root))
        self.assertEqual(len(first),201)
        self.assertEqual(len({c['id'] for c in first}),201)
        for case in first:
            if 'committed' in case:self.assertEqual(oracle(case['args']),case['committed'],case['id'])

if __name__=='__main__':unittest.main()
