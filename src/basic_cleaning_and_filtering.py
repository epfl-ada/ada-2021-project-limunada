# -*- coding: utf-8 -*-
"""basic_cleaning_and_filtering.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1p3u2VrS1-aoQLFgDmm_zwgM1Sj9jLqTp

## Installing and importing dependencies, mounting to drive
"""

!pip install pyarrow
!pip install Wikidata
!pip install google.drive

# !pip install tld
# !pip install aspect_based_sentiment_analysis

import numpy as np 
import pandas as pd
import matplotlib.pyplot as plt 
import json
import os
import bz2
import itertools 

from google.colab import drive
drive.mount('/content/drive')

from wikidata.client import Client
WIKI_CLIENT = Client()

"""## Load Quotebank and discard 'None' speakers

First, we want to load the Quotebank dataset (years 2015 - 2020) and discard 
all the quotes for which the most probable speaker is unidentified ('None').

We save the resulting quotes into files whose names are formatted as 'quotes-no-nones-{year}.json.bz2'
"""

# Iterate through the years of existing Quotebank files
for year in range(2015, 2021):

  path_to_file = f'/content/drive/MyDrive/Quotebank/quotes-{year}.json.bz2' 
  path_to_out = f'/content/drive/MyDrive/Quotebank_limunADA/quotes-no-nones-{year}.json.bz2'

  # If the output file for the current year already exists, skip it
  if os.path.isfile(path_to_out):
    print(f'\nFile for year {year} already exists. Moving on...')
    continue

  print(f'\nExtracting non-None quotations for year {year}')

  # Iterate through the quotes
  with bz2.open(path_to_file, 'rb') as s_file:
    with bz2.open(path_to_out, 'wb') as d_file:
      for instance in s_file:

        # loading a sample and checking the speaker
        instance = json.loads(instance) 
        if instance['speaker'] == 'None':
          continue

        # writing in the new file
        d_file.write((json.dumps(instance)+'\n').encode('utf-8'))

"""## Speaker attributes parquet"""

# Load the provided parquet file with information (QIDs) about each of the speakers
parquet_path = '/content/drive/MyDrive/Project datasets/speaker_attributes.parquet'
speakers_attributes = pd.read_parquet(parquet_path)

speakers_attributes.head()

"""## Enriching Quotebank using Wikidata
We leverage the fact that we can easily enrich the Quotebank dataset by incorporating Wikidata into it. This is done by identifying the QID of the speaker (for a given quote), and then referring to the provided .parquet file with per-speaker information. 

The following columns are added to each quote information:    
* age
* nationality
* party
* academic degree
* ethnicity
* gender

NOTE - before doing that, we have to adopt a way to disambiguate the relation between speaker names and their corresponding QIDs (since there can be multiple QIDs mapped to a single speaker name). The method that we adopted is taking the QID with the smallest number, implying that it was created the earliest. There are also other heuristics that could be used, but we stuck with this one throughout the process.

### Wikidata API

Here, we used the Wikidata API to get the desired QID-label mappings. However, in the meantime, ADA staff provided us with a big .csv file with all these human-interpretable labels, so we will move to that approach when working on Milestone 3. Anyways, we are showing this, since we implemented it before getting the files from TAs, it would be a waste otherwise. :)
"""

def get_min_qid(qids):
  """
  Returns the QID with the smallest integer part.
  """
  qids_int = [int(qid.replace('Q', '')) for qid in qids]
  return f'Q{min(qids_int)}'


def map_qids_to_labels(qids, wiki_client=WIKI_CLIENT):
  """
  Given a set or list of QIDs, return a dictionary of format: {QID: label}
  We get the labels for each QID using the Wikidata client.
  """
  qids_labels_dict = dict()
  for qid in qids:
    try:
      # Multilingual to basic string
      qids_labels_dict[qid] = str(wiki_client.get(qid, load=True).label)
    except Exception:
      # In case the QID doesn't exist on Wikidata
      print(f'Problem with {qid}. Skipping...')

  return qids_labels_dict 


def add_wikidata_column_to_quote(
    quote_data_original, 
    column_name, 
    speakers_attributes,
    inplace=False,
    ignore_existing=True,
    is_qid=True
    ):
  """
  This functions takes as input a dictionary corresponding to a single quote 
  (with all the information that goes with it - 'speaker', 'qids', ...),
  a column name that we wish to add to the quote, depending on its speaker,
  and attributes for all speakers.
  It finds the speaker QID, accesses its attributes, and either takes the raw 
  values from the desired column (is_qid==False), or queries those QIDs and
  takes the corresponding human-interpretable labels (is_qid==True).
  """
  if inplace:
    quote_data = quote_data_original
  else:
    quote_data = quote_data_original.copy()

  # If we're not OK with overwriting the existing column, raise an exception
  if not ignore_existing:
    if column_name in quote_data:
      raise Exception(f'Provided column name "{column_name}" already exists!')

  # Raise an exception if the column name doesn't exist in speaker attributes
  if not column_name in speakers_attributes.columns:
    err_msg = f'Provided column name "{column_name}" does not exist in the '
    err_msg += 'provided speaker atttributes DataFrame!'
    raise Exception(err_msg)

  quote_data[column_name] = []

  # Get the 'correct' speaker QID and the corresponding speaker attributes
  speaker_qid = get_min_qid(quote_data['qids'])
  curr_speaker_attributes = speakers_attributes[
    speakers_attributes['id'] == speaker_qid
    ]

  # None check
  if curr_speaker_attributes[column_name].values[0] is None:
    return quote_data

  # If the column value is expected to be QID, query it using Wikidata API
  # If not, just take the raw values
  if is_qid:
    labels = map_qids_to_labels(
        curr_speaker_attributes[column_name].values[0].tolist()
        )
  else:
    labels_list = curr_speaker_attributes[column_name].values[0].tolist()
    labels = {i: val for i, val in enumerate(labels_list)}
  
  # Assign the labels to the new column
  for qid in labels:
    quote_data[column_name].append(labels[qid])

  return quote_data

"""### Example of enriching the data
We provide a small example to demonstrate our Wikidata-enriching functions, to add the desired speaker attributes mentioned above. We divide them into columns that are represented as QIDs (needs querying) and that are not (does not need querying).
"""

# Define the columns that we want to add to the existing data
QID_COLUMNS_TO_ADD = [
  'nationality', 'party', 'ethnic_group', 'academic_degree', 'gender'
  ]
NON_QID_COLUMNS_TO_ADD = ['date_of_birth']

# Number of instances to process in this example
SAMPLES_TO_PROCESS = 10

year = 2019
path_to_file = f'/content/drive/MyDrive/Quotebank_limunADA/quotes-no-nones-{year}.json.bz2'
running_df = pd.DataFrame()

# Iterate through the quotes
with bz2.open(path_to_file, 'rb') as s_file:
  for i, instance in enumerate(s_file):
    # Loading a sample and checking the speaker
    instance = json.loads(instance) 

    # Add the columns that require querying with Wikidata API
    for column_to_add in QID_COLUMNS_TO_ADD:
      add_wikidata_column_to_quote(
        instance, column_to_add, speakers_attributes, inplace=True
        )
    
    # Add the columns that don't require querying
    for column_to_add in NON_QID_COLUMNS_TO_ADD:
      add_wikidata_column_to_quote(
        instance, column_to_add, speakers_attributes, inplace=True, is_qid=False
        )
    
    # Append the current instance to the running data frame
    curr_df = pd.DataFrame([{k: str(v) for k, v in instance.items()}])
    running_df = pd.concat([running_df, curr_df])

    if i == SAMPLES_TO_PROCESS:
      break 

running_df.head(SAMPLES_TO_PROCESS)

