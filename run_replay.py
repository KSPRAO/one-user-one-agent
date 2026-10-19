import argparse,os,subprocess,sys
from src.agent import run
from src.reporting import judge_outcomes,make_impact_report
from src.data_audit import audit
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',default='sample_run');p.add_argument('--seed',default='oua-practice');a=p.parse_args();run('.',a.out);audit('.',a.out);sim=a.out+'/simulator'
 subprocess.run([sys.executable,'simulator/simulate_outcomes.py','--pack','.','--actions',a.out+'/actions.jsonl','--out',sim,'--seed',a.seed],check=True)
 judge_outcomes(a.out,sim);make_impact_report('.',a.out,sim);print('Replay complete:',a.out)
if __name__=='__main__':main()
