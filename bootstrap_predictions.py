import numpy as np
import pandas as pd

from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.utils import resample
from util.utils import get_calibration_metrics, stat_ci, stat_pval

import argparse
import os
import time

def bootstrap_predictions(n_bootstrap, out_file, output_dir=""):

    text_files=[fname for fname in os.listdir(dir_path) if fname.startswith('result_') and fname.endswith(".txt")]

    with open(os.path.join(output_dir, out_file), "w") as out_file:
        for target in targets:
            for representation in representations:
                for text_file in sorted(text_files):
                    if target not in text_file:
                        continue
                    if (representation in text_file):
                        print(target, representation)

                        with open(os.path.join(dir_path, text_file), 'rb') as f:
                            all_lines=f.readlines()

                        for modeltype in models:
                            print('modeltype=', modeltype)
                            model_lines=[line.decode() for line in all_lines if modeltype.upper() in line.decode()]
                            for hosp in hospitals:
                                for year in year_range:
                                    for month in month_intervals:
                                        lines=[line for line in model_lines if (hosp in line) and 
                                            (str(year) in line.split(",")[5]) and
                                            (line.split("<")[1].split(">")[0] == ','.join([str(m) for m in np.arange(month-month_step+1, month+1, 1)]))
                                            ]
                                        if len(lines)==0:
                                            continue
                                        label=pred=y_pred_prob=None
                                        for line in lines:
                                            try:
                                                if ('label,' in line):
                                                    label=line.split("label")[1].split("<")[1].split(">")[0].split(",")
                                                    label=np.array([int(float(i)) for i in label])
                                                if ('pred,' in line):
                                                    pred=line.split("pred,")[1].split("<")[1].split(">")[0].split(",")
                                                    pred=np.array([float(i) for i in pred])
                                                if ('y_pred_prob,' in line):
                                                    y_pred_prob=line.split("y_pred_prob,")[1].split("<")[1].split(">")[0].split(",")
                                                    y_pred_prob=np.array([float(i) for i in y_pred_prob])
                                            except:
                                                print(line)
                                                print(hosp, year, month, target, modeltype, representation)
                                                raise
                                        if (label is None) or (np.unique(label).size < 2):
                                            continue
                                        auroc_list=[]
                                        auprc_list=[]
                                        ece_list=[]

                                        auroc_list.append(roc_auc_score(label, y_pred_prob))
                                        auprc_list.append(average_precision_score(label, y_pred_prob))
                                        try:
                                            _,_,ece,_=get_calibration_metrics(label, y_pred_prob,n_bins=10,bin_strategy='quantile')
                                            ece_list.append(ece)
                                        except:
                                            pass
                                        print('bootstrapping (',hosp, year, month,')')
                                        for i in range(n_bootstrap):
                                            # indices=np.random.randint(0, len(label), len(label))
                                            indices=resample(range(len(label)),random_state=i,n_samples=len(label),replace=True,stratify=label)
                                            y_true=label[indices]
                                            y_pred=pred[indices]
                                            probs=y_pred_prob[indices]
                                            auroc_list.append(roc_auc_score(y_true, probs))
                                            auprc_list.append(average_precision_score(y_true, probs))
                                            try:
                                                _,_,ece,_=get_calibration_metrics(y_true, probs,n_bins=10,bin_strategy='quantile')
                                                ece_list.append(ece)
                                            except:
                                                pass

                                        out_file.write('target, {}, representation, {}, model, {}, hospital, {}, year, {}, month, {}, AUROC, <{}> \r\n'.format(
                                        target, representation, modeltype.upper(), hosp, str(year), str(month), ",".join([str(i) for i in auroc_list])))

                                        out_file.write('target, {}, representation, {}, model, {}, hospital, {}, year, {}, month, {}, AUPRC, <{}> \r\n'.format(
                                        target, representation, modeltype.upper(), hosp, str(year), str(month), ",".join([str(i) for i in auprc_list])))

                                        out_file.write('target, {}, representation, {}, model, {}, hospital, {}, year, {}, month, {}, ECE, <{}> \r\n'.format(
                                        target, representation, modeltype.upper(), hosp, str(year), str(month), ",".join([str(i) for i in ece_list])))

    return

def bootstrap_preds_to_stats(bs_file, stats_file, stat_test="mannwhitneyu", output_dir=""):
    '''
    supported stat_tests are ["wicoxon", "mannwhitneyu"]
    '''
    
    with open(os.path.join(dir_path, bs_file), "r") as f:
        all_lines=f.readlines()
    
    base_hospital='UPMCPUH'
    base_year=2011
    base_month=2

    columns=[]
    for target in targets:
        for model in models:
            for rep in representations:
                for measurement in measures:
                    for stat in stats:
                        columns.append((target,model, rep, measurement, stat))

    ind=[(hosp, yr, mnth) for hosp in hospitals for yr in year_range for mnth in month_intervals]
    ind=pd.MultiIndex.from_tuples(ind, names=('hospital', 'year', 'month'))
    cols=pd.MultiIndex.from_tuples(columns, names=('target', 'model', 'representation', 'measurement', 'stat'))
    result_df=pd.DataFrame(index=ind, columns=cols)

    for target in targets:
        for modeltype in models:
            for rep in representations:
                for measure in measures:
                    print(target, rep, modeltype, measure)
                    lines=[l for l in all_lines if (target in l) and (rep in l.split(",")[3]) and
                        (modeltype.upper() in l.split(",")[5]) and (measure in l.split(",")[12])]
                    base_line=[line for line in lines if (base_hospital in line.split(",")[7]) and
                            (str(base_year) in line.split(",")[9]) and (int(line.split(",")[11].strip()) == base_month)][0]
                    base_values=get_values_from_line(base_line)
                    if len(base_values)==0:
                        continue
                    for line in lines:
                        values=get_values_from_line(line)
                        if len(values)==0:
                            continue
                        hosp=line.split(",")[7].strip()
                        year=int(line.split(",")[9].strip())
                        month=int(line.split(",")[11].strip())
                        mean_score, ci_lower, ci_upper=stat_ci(values)
                        _, pval=stat_pval(values, base_values, test=stat_test)
                        # print(hosp,year,month,target, rep, modeltype, measure, mean_score, ci_lower, ci_upper, pval)
                        result_df.loc[(hosp,year,month), idx[target, modeltype, rep, measure, ['N','mean', 'CI_L','CI_U', 'pval']]]=(len(values), mean_score, ci_lower, ci_upper, pval)
                result_df.to_csv(os.path.join(output_dir, stats_file))
                result_df.to_pickle(os.path.join(output_dir, stats_file.split(".")[0]+'.pkl'))
    return

def get_values_from_line(line):
    if len(line)==0:
        values=[]
    else:
        values=line.split("<")[1].split(">")[0]
        if values=='':
            values=[]
        else:
            values=[float(i) for i in values.split(",")]
    return values


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='booststrap predictions of the overtime-hospital experiment')
    parser.add_argument('--run_bootstrap', type=int, default=0, help="run bootstrap or read from existing file. 0: read from existing file, 1: run bootstrap")
    parser.add_argument('--n_bootstrap', type=int, default=100, help="num of bootstrap samples")
    parser.add_argument('--generate_stats', type=int, default=1, help="generate stats from bootstrap. 0: False, 1: True")
    parser.add_argument('--stat_test', type=str, default="mannwhitneyu", choices=["mannwhitneyu", "wilcoxon"], help="independent test to use to compare vector of metrics")
    parser.add_argument('--dir_path', type=str, default="", help="full path to directory containing probability and label files and/or generated bootstraps")
    parser.add_argument('--output_dir', type=str, default="", help="full path to output directory")

    args = parser.parse_args()
    
    targets = ['mort_icu', 'los_3']
    representations = ['raw', 'pca']
    models=['rf','lr','nb','rbf-svm']
    measures=['AUROC', 'AUPRC', 'ECE']
    stats=['N','mean', 'CI_L', 'CI_U', 'pval']

    hospitals = ['UPMCBED','UPMCEAS','UPMCHAM','UPMCHZN','UPMCMCK','UPMCMER','UPMCMWH','UPMCNOR','UPMCPAS','UPMCPUH','UPMCSHY','UPMCSMH']
    year_range = np.arange(2011, 2015)
    month_step = 2
    month_intervals = np.arange(month_step, 13, month_step)

    dir_path=args.dir_path
    output_dir=args.output_dir
    if output_dir=="":
        output_dir=dir_path
    
    bs_file="stratified_bootstrap_metrics.txt"
    stats_file="bootstrap_stats_" + args.stat_test + ".csv"
    
    idx=pd.IndexSlice

    t0=time.time()
    if(args.run_bootstrap==1):
        print("running bootstrap ...")
        bootstrap_predictions(n_bootstrap=args.n_bootstrap, out_file=bs_file, output_dir=output_dir)
    if(args.generate_stats==1):
        print("generating stats from bootstrap samples...")
        bootstrap_preds_to_stats(bs_file=bs_file, stats_file=stats_file, stat_test=args.stat_test, output_dir=output_dir)
    
    t1=time.time()
    print("Done. in {} seconds".format(str(t1-t0)))




