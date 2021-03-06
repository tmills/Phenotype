#!/usr/bin/env python3

# reproducible results
import numpy as np
import random as rnd
import tensorflow as tf
np.random.seed(1337)
rnd.seed(1337)
tf.set_random_seed(1337)
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['PYTHONHASHSEED'] = '0'
from keras import backend as bke
s = tf.Session(graph=tf.get_default_graph())
bke.set_session(s)

# rest of the imports
import sys
sys.path.append('../Lib/')
sys.dont_write_bytecode = True
import configparser
from sklearn.metrics import f1_score
import keras as k
from keras.preprocessing.sequence import pad_sequences
from keras.models import Sequential
from keras.layers.core import Dense, Activation, Dropout
from keras.layers.embeddings import Embedding
from keras.layers import Conv1D, GlobalMaxPooling1D
from keras import optimizers
from random_search import RandomSearch
import dataset, word2vec

# ignore sklearn warnings
def warn(*args, **kwargs):
  pass
import warnings
warnings.warn = warn

RESULTS_FILE = 'Model/results.txt'
MODEL_FILE = 'Model/model.h5'

class CnnCodePredictionModel:

  def __init__(self):
    """Configuration parameters"""

    self.configs = {};

    self.configs['batch'] = (1, 2)
    self.configs['filters'] = (256, 512, 1024)
    self.configs['filtlen'] = (1, 2, 3, 4, 5, 6, 7)
    self.configs['hidden'] = (256, 512, 1024, 2048)
    self.configs['optimizer'] = ('rmsprop', 'adam', 'adamax', 'nadam')
    self.configs['lr'] = (0.0001, 0.001, 0.01, None)
    self.configs['activation'] = ('relu', 'tanh', 'sigmoid', 'linear')
    self.configs['dropout'] = (0, 0.25, 0.5)
    self.configs['embed'] = (True, False)

  def get_random_config(self):
    """Random training configuration"""

    config = {};

    config['batch'] = rnd.choice(self.configs['batch'])
    config['filters'] = rnd.choice(self.configs['filters'])
    config['filtlen'] = rnd.choice(self.configs['filtlen'])
    config['hidden'] = rnd.choice(self.configs['hidden'])
    config['optimizer'] = rnd.choice(self.configs['optimizer'])
    config['lr'] = rnd.choice(self.configs['lr'])
    config['activation'] = rnd.choice(self.configs['activation'])
    config['dropout'] = rnd.choice(self.configs['dropout'])
    config['embed'] = rnd.choice(self.configs['embed'])

    return config

  def get_model(self, init_vectors, vocab_size, input_length, output_units, config):
    """Model definition"""

    model = Sequential()
    model.add(Embedding(input_dim=vocab_size,
                        output_dim=300,
                        input_length=input_length,
                        trainable=True,
                        weights=init_vectors,
                        name='EL'))
    model.add(Conv1D(
      filters=config['filters'],
      kernel_size=config['filtlen'],
      activation='relu'))
    model.add(GlobalMaxPooling1D(name='MPL'))

    model.add(Dense(config['hidden'], name='HL'))
    model.add(Activation(config['activation']))

    # dropout on the fully-connected layer
    model.add(Dropout(config['dropout']))

    model.add(Dense(output_units))
    model.add(Activation('sigmoid'))

    return model

  def get_optimizer(self, optimizer, learning_rate):
    """Get optimizer by name"""

    if optimizer == 'rmsprop':
      if learning_rate == None:
        return optimizers.RMSprop()
      else:
        return optimizers.RMSprop(lr=learning_rate)
    elif optimizer == 'adam':
      if learning_rate == None:
        return optimizers.Adam()
      else:
        return optimizers.Adam(lr=learning_rate)
    elif optimizer == 'adamax':
      if learning_rate == None:
        return optimizers.Adamax()
      else:
        return optimizers.Adamax(lr=learning_rate)
    elif optimizer == 'nadam':
      if learning_rate == None:
        return optimizers.Nadam()
      else:
        return optimizers.Nadam(lr=learning_rate)
    else:
      return None

  def run_one_eval(self, train_x, train_y, valid_x, valid_y, epochs, config):
    """A single eval"""

    print(config)

    init_vectors = None
    if config['embed']:
      embed_file = os.path.join(base, cfg.get('data', 'embed'))
      w2v = word2vec.Model(embed_file)
      init_vectors = [w2v.select_vectors(provider.token2int)]

    vocab_size = train_x.max() + 1
    input_length = max([len(seq) for seq in x])
    output_units = train_y.shape[1]

    model = self.get_model(init_vectors,
                           vocab_size,
                           input_length,
                           output_units,
                           config)
    model.compile(loss='binary_crossentropy',
                  optimizer=self.get_optimizer(
                    config['optimizer'],
                    config['lr']),
                  metrics=['accuracy'])
    model.fit(train_x,
              train_y,
              epochs=epochs,
              batch_size=config['batch'],
              validation_split=0.0,
              verbose=0)

    # probability for each class; (test size, num of classes)
    # batch_size needed because large batches cause OOM
    distribution = model.predict(valid_x, batch_size=8)

    # turn into an indicator matrix
    distribution[distribution < 0.5] = 0
    distribution[distribution >= 0.5] = 1

    f1 = f1_score(valid_y, distribution, average='macro')
    print('f1: %.3f after %d epochs\n' % (f1, epochs))

    return 1 - f1

if __name__ == "__main__":

  # fyi this is a global variable now
  cfg = configparser.ConfigParser()
  cfg.read(sys.argv[1])

  base = os.environ['DATA_ROOT']
  train_dir = os.path.join(base, cfg.get('data', 'train'))
  code_file = os.path.join(base, cfg.get('data', 'codes'))

  provider = dataset.DatasetProvider(
    train_dir,
    code_file,
    cfg.getint('args', 'min_token_freq'),
    cfg.getint('args', 'max_tokens_in_file'),
    cfg.getint('args', 'min_examples_per_code'),
    use_cuis=False)
  x, y = provider.load(tokens_as_set=False)

  maxlen = max([len(seq) for seq in x])
  x = pad_sequences(x, maxlen=maxlen)
  y = np.array(y)

  print('x shape:', x.shape)
  print('y shape:', y.shape)
  print('max seq len:', maxlen)
  print('vocab size:', x.max() + 1)
  print('number of features:', len(provider.token2int))
  print('number of labels:', len(provider.code2int))

  model = CnnCodePredictionModel()
  search = RandomSearch(model, x, y)
  best_config = search.optimize(max_iter=64)
  print('best config:', best_config)
