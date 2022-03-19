#
# dashboard_app_run_pipeline
#
# Dashboard for kicking off pipelines
#
import sys, os, csv, uuid, socket
import dash
from dash import dash_table
from dash import dcc
from dash import html
from dash.dependencies import Input, Output, State
import pandas as pd
import flask
sys.path.append(os.path.join(sys.path[0],'..','..','global_utils','src'))
import file_utils
sys.path.append('../../dashboard_utils/src/')
sys.path.append('../../dashboard_utils/src/global_utils/src/')
import dashboard_file_utils as dfu
import dashboard_server_utils as dsu
sys.path.append(os.path.join(sys.path[0],'..','..','batch','src'))
# sys.path.append('../../batch/src/')
import run_pipeline

SERVER_PORT = '5001'
isSubmitted = 'false'

pipeline_list = [{'label': 'Targeted DNA-Seq', 'value': 'dnaseq_targeted'},
              {'label': 'ChIP-Seq', 'value': 'chipseq'}]

app = dash.Dash(__name__, suppress_callback_exceptions=True)

def serve_layout():
    return html.Div([
        html.H3('Hubseq Pipeline Dashboard'),
        html.H5('Choose a bioinformatics pipeline and select sequencing runs and samples.'),
        dcc.Dropdown(id='choose-pipeline',
                     options=pipeline_list,
                     value=pipeline_list[0]['value'],
                     placeholder = "Choose Pipeline"),
        dcc.Dropdown(id='choose-runs',
                     placeholder = "Choose Runs",
                     multi=True),
        dcc.Dropdown(id='choose-samples',
                     placeholder = "Choose Samples",
                     searchable=True,
                     multi=True),
        dcc.Checklist(id='choose-all-samples',
                      options=[{'label': 'Choose All Samples', 'value': 'allsamples'}],
                      value=[],
                      labelStyle={'display': 'inline-block'}),
        html.P(''),
        html.P('SELECT BIOINFORMATICS MODULES TO RUN:'),    
        html.Div(id='dockerlistdiv', style={'width': '100%'}, children=[]),
        html.P('======================================================='),    
        html.P(''),
        html.Div(id='buttons', children = [
            html.Button("Edit Program Parameters", id="advanced_button", style={"margin": "5px"}),            
            html.Button("Run Pipeline", id="run_pipeline_button", style={"margin": "5px", "background-color": "yellow"})
            ]),
        html.P('submitted-status', id='submitted-status', style={'display': 'none'}, key=isSubmitted),
    ])


app.layout = serve_layout

teamid = 'npipublicinternal'
userid = 'test'

def getRunIds( root_folder, teamid, userid, pipe ):
    # sub until we fix file_utils getRunIds()
    maindir = os.path.join(root_folder, teamid, userid, pipe)
    dirs = os.listdir(maindir)
    print('DIRS: '+str(dirs))
    dirs_final = []
    for d in dirs:
        if d.rstrip('/') != 'fastq' and os.path.isdir(os.path.join(maindir,d)):
            dirs_final.append(d)
    return dirs_final


def getSamples(root_folder,teamid,userid,pipe,rids):
    # sub until we fix file_utils version
    # returns run: sample list
    dirs_final = []    
    for rid in rids:
        maindir = os.path.join(root_folder, teamid, userid, pipe,rid)
        dirs = os.listdir(maindir)
        for d in dirs:
            if os.path.isdir(os.path.join(maindir,d)) and d not in ['bam','fastq']:
                dirs_final.append(rid+': '+d)
    return dirs_final


def getInputFiles(teamid,userid,pipeline,sampleids):
    # all sample input files, as list of lists
    input_files = []
    for rid_sid in sampleids:
        sample_fastq_files = []
        rid = rid_sid.split(':')[0]
        sid = rid_sid.split(':')[1].lstrip(' ')
        fastq_dir_local = os.path.join('/s3/',teamid,userid,pipeline,rid,'fastq')
        fastq_dir_remote = os.path.join('s3://',teamid,userid,pipeline,rid,'fastq')        
        fastq_files_all = os.listdir(fastq_dir_local)
        for f in fastq_files_all:
            if sid in f and ('.fq' in f or '.fastq' in f):
                sample_fastq_files.append(os.path.join(fastq_dir_remote,f))
        sample_fastq_files.sort() # R1 before R2
        input_files.append(sample_fastq_files)
    return input_files

@app.callback(
    Output('submitted-status', 'key'),
    Input("run_pipeline_button", "n_clicks"),
    State('choose-pipeline', 'value'),
    State('choose-samples', 'value'),
    State('choose-modules', 'value'),
    prevent_initial_call=True)
def click_run_pipeline(n_clicks, pipeline, sampleids, modules):
    global teamid, userid
    print('IN CLICK RUN PIPELINE - N-CLICKS {}'.format(str(n_clicks)))
    if n_clicks != None and n_clicks > 0:
        all_input_files = getInputFiles(teamid,userid,pipeline,sampleids)
        print('ALL INPUT FILES: '+str(all_input_files))
        for sample_fastq_files in all_input_files:
            pipeline_json = {'pipeline': pipeline, 'teamid': teamid, 'userid': userid, 'modules': ','.join(modules),
                             'input': ','.join(sample_fastq_files),
                             'samples': ','.join(list(map(lambda x: x.replace(' ',''), sampleids)))}
            run_pipeline.run_pipeline( pipeline_json )
        return 'true'
    else:
        return 'false'


@app.callback(
    Output('choose-samples', 'value'),
    Input('choose-pipeline', 'value'),
    Input('choose-runs', 'value'),
    Input('choose-all-samples', 'value'))
def choose_all_samples( pipeline, runs, all_samples_checked ):
    global teamid, userid
    if all_samples_checked != None and pipeline != None and runs != None and 'allsamples' in all_samples_checked:
        return getSamples('/s3', teamid, userid, pipeline, runs)
    else:
        return []
            
@app.callback(
    Output('choose-runs', 'options'),
    Input('choose-pipeline', 'value'))
def choose_pipeline(selected_pipeline):
    global teamid, userid
    if selected_pipeline != [] and selected_pipeline != None:    
        return dsu.list2optionslist(getRunIds('/s3/', teamid, userid, selected_pipeline))
    else:
        return []

    
@app.callback(
    Output('choose-samples', 'options'),
    Input('choose-runs', 'value'),
    Input('choose-pipeline', 'value'))
def choose_samples(selected_runs, pipeline):
    print('RUNS: '+str(selected_runs))
    if selected_runs != [] and selected_runs != None:
        return dsu.list2optionslist(getSamples('/s3', teamid, userid, pipeline, selected_runs))
    else:
        return []

    
@app.callback(
    Output('dockerlistdiv', 'children'),
    Input('choose-pipeline', 'value'))
def choose_modules( selected_pipeline ):
    _dc = []
    print('IN CHOOSE MODULES: {}'.format(selected_pipeline))
    if selected_pipeline == 'dnaseq_targeted':
        _dc.append(dcc.Checklist(id='choose-modules',
                                 options=[{'label': 'FASTQC  ', 'value': 'fastqc'},
                                      {'label': 'Alignment (BWA MEM)', 'value': 'bwamem'},                                    
                                      {'label': 'Read Pileup (mpileup)  ', 'value': 'mpileup'},
                                      {'label': 'Variant Calling (varscan2)', 'value': 'varscan2'}
                             ],
                             value=[],
                             labelStyle={'display': 'inline-block', 'margin': '3px'}))
    elif selected_pipeline == 'chipseq':
        _dc.append(dcc.Checklist(id='choose-modules',
                                 options=[{'label': 'FASTQC  ', 'value': 'fastqc'},
                                      {'label': 'Alignment (bowtie2)  ', 'value': 'bowtie2'},   
                                      {'label': 'Peak Finding with HOMER   ', 'value': 'homer'},
                                      {'label': 'Peak Finding with MACS2  ', 'value': 'macs2'},
                             ],
                             value=[],
                             labelStyle={'display': 'inline-block', 'margin': '3px'}))
    return _dc


if __name__ == "__main__":
    local_ip = socket.gethostbyname(socket.gethostname())
    app.run_server(host=local_ip, port=SERVER_PORT, debug=False, dev_tools_ui=False, dev_tools_props_check=False)
