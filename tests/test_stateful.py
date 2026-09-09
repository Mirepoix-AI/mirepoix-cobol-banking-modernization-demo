import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from stateful import initial,expected_step,validate_state,validate_fixture,encode,decode

class StatefulContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture=json.loads((Path(__file__).resolve().parents[1]/'fixtures/stateful.json').read_text())
        self.states=[initial(self.fixture)]
        for row in self.fixture['records']:self.states.append(expected_step(self.states[-1],row))

    def test_explicit_journal_priority_and_overflow(self):
        journal=self.states[-1]['journal']
        self.assertEqual([r['reason'] for r in journal[:8]],
            [None,'ACCEPTED_ID','UNKNOWN_ACCOUNT','INVALID_INPUT',None,'INTEREST_OVERFLOW','BALANCE_OVERFLOW',None])
        self.assertEqual([journal[1][k] for k in ['opening','interest','closing']],[None,None,None])
        self.assertEqual(journal[6]['interest'],'9999999.99')
        self.assertEqual(journal[9]['reason'],'RATE_OVERFLOW')
        for state in self.states:validate_state(state,self.fixture)

    def test_bookkeeping_corruption_refused(self):
        for field,value in [('next',True),('acceptedIds',[]),('inputHash','0'*64),('balances',{'A':'666.00'})]:
            state=copy.deepcopy(self.states[1]);state[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_state(state,self.fixture)
        state=copy.deepcopy(self.states[2]);state['journal'][1]['opening']='0.00'
        with self.assertRaises(ValueError):validate_state(state,self.fixture)

    def test_wire_delimiters_and_input_bounds(self):
        for rate in ['', '|', '\r', ' 1.00 ', 'x'*64]:
            fixture=copy.deepcopy(self.fixture);fixture['records']=[dict(id='x',account='A',rate=rate)]
            validate_fixture(fixture)
            state=expected_step(initial(fixture),fixture['records'][0])
            wire=encode(state,fixture['records'][0]).split('RECORD|')[0]+'END\n'
            self.assertEqual(decode(wire),state)
        for rate in ['x'*65,'\n','\t','\0','é']:
            fixture=copy.deepcopy(self.fixture);fixture['records'][0]['rate']=rate
            with self.subTest(rate=rate),self.assertRaises(ValueError):validate_fixture(fixture)
