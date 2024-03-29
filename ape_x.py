import tensorflow as tf
from IPython.display import clear_output
import tensorflow_probability as tfp
import numpy as np
import pandas as pd
from statistics import mean
from sklearn.preprocessing import MinMaxScaler
from sklearn.preprocessing import StandardScaler
from net import *
from memory import *
# from reward_ditect import *
from reward import *
from collections import deque
import random
from sac_model import *
import time
import logging
import shutil


####################################################################################################################################

class Actor:
    LEARNING_RATE = 1e-4
    GAMMA = 0.99
    MEMORY_SIZE = 10000

    def __init__(self, path, window_size, num,epsilon, sess,STEP_SIZE=480,OUTPUT_SIZE=3, save=False, saver_path=None, restore=False, noise=True, norm=True, ent_coef='auto', target_entropy='auto'):
        self.path = path
        self.window_size = window_size
        self.STEP_SIZE = STEP_SIZE
        self.OUTPUT_SIZE = OUTPUT_SIZE
        self.rand = np.random.RandomState()
        self._preproc()
        self.state_size = (None, self.window_size, self.df.shape[-1])
        self.EPSILON = epsilon
        print("num: ",num)
        self.num= num
        self.rewards = reward
        self.action_noise = 0.3
        self.noise_clip = 0.5
        self.act_noise = 0.4
        self.best_pip = None
        self.ent_coef = ent_coef
        self.target_entropy = target_entropy
        # tf.reset_default_graph()
        self.sess = sess
        tf.get_logger().setLevel(logging.ERROR)

        with tf.device('/cpu:0'):
            with tf.variable_scope("input"):
              self.policy_tf = Actor_Critic(norm,noise)
              self.target_policy = Actor_Critic(norm,noise)

              self.state = tf.placeholder(tf.float32, self.state_size)
              self.new_state = tf.placeholder(tf.float32, self.state_size)
              self.initial_state = tf.placeholder(tf.float32,(None,512))
              self.action = tf.placeholder(tf.float32,(None,self.OUTPUT_SIZE))
              self.reward = tf.placeholder(tf.float32,(None,1))
              self.accuracy = tf.placeholder(tf.float32,(None,1))

            with tf.variable_scope("model", reuse=False):
            #   self.deterministic_policy, self.policy_out, logp_pi, self.entropy, self.last_state
              self.tuple = self.policy_tf.actor(
                  self.state,self.initial_state,self.OUTPUT_SIZE,"actor")
              self.deterministic_action, self.policy_out, logp_pi, self.entropy, self.last_state = self.tuple[0],self.tuple[1],self.tuple[2],self.tuple[3],self.tuple[4]
              qf1, qf2, value_fn = self.policy_tf.critic(self.state, self.initial_state, self.action, create_vf=True, create_qf=True,name="critic")
              qf1_pi, qf2_pi, _ = self.policy_tf.critic(
                  self.state, self.initial_state, self.policy_out, create_vf=True, create_qf=True, name="critic")
              self.qf = qf1_pi

            if self.target_entropy == 'auto':
                # automatically set target entropy if needed
                self.target_entropy = -np.prod(self.OUTPUT_SIZE).astype(np.float32)
            else:
                # Force conversion
                # this will also throw an error for unexpected string
                self.target_entropy = float(self.target_entropy)

            # The entropy coefficient or entropy can be learned automatically
            # see Automating Entropy Adjustment for Maximum Entropy RL section
            # of https://arxiv.org/abs/1812.05905
            if isinstance(self.ent_coef, str) and self.ent_coef.startswith('auto'):
                # Default initial value of ent_coef when learned
                init_value = 1.0
                if '_' in self.ent_coef:
                    init_value = float(self.ent_coef.split('_')[1])
                    assert init_value > 0., "The initial value of ent_coef must be greater than 0"

                self.log_ent_coef = tf.get_variable('log_ent_coef', dtype=tf.float32,
                                                    initializer=np.log(init_value).astype(np.float32))
                self.ent_coef = tf.exp(self.log_ent_coef)
            else:
                # Force conversion to float
                # this will throw an error if a malformed string (different from 'auto')
                # is passed
                self.ent_coef = float(self.ent_coef)

            with tf.variable_scope("target", reuse=False):
              _, policy_out, _, _,_ = self.target_policy.actor(
                  self.new_state,self.initial_state,self.OUTPUT_SIZE,"actor")
              action_noise = tf.random_normal(tf.shape(policy_out), stddev=self.action_noise)
              action_noise = tf.clip_by_value(action_noise, -self.noise_clip, self.noise_clip)
              noisy_action = tf.clip_by_value(policy_out + action_noise, -1, 1)
              target_qf1,target_qf2,target_vf = self.target_policy.critic(self.new_state,self.initial_state,noisy_action,create_qf=True, create_vf=True)
            with tf.variable_scope("loss"):
                min_qf_pi = tf.minimum(qf1_pi, qf2_pi)
                min_qf = tf.minimum(target_qf1, target_qf2)
                q_backup = tf.stop_gradient(
                        self.reward + self.GAMMA * target_vf
                )
                qf1_loss = tf.abs(0.5 * tf.reduce_mean((q_backup - qf1) ** 2))
                self.qf1_loss = qf1_loss
                qf2_loss = tf.abs(0.5 * tf.reduce_mean((q_backup - qf2) ** 2))

                self.absolute_errors = tf.abs(q_backup - qf1)

                ent_coef_loss = - tf.reduce_mean(self.log_ent_coef * tf.stop_gradient(logp_pi + self.target_entropy))

                policy_kl_loss = (tf.reduce_mean(self.ent_coef * logp_pi - qf1_pi))
                v_backup = tf.reduce_mean(min_qf_pi - self.ent_coef * logp_pi)
                value_loss = tf.abs(0.5 * tf.reduce_mean((value_fn - v_backup) ** 2))
                self.policy_loss = policy_kl_loss
                self.values_losses = qf1_loss + qf2_loss + value_loss

        self.actor_optimizer = tf.train.AdamOptimizer(self.LEARNING_RATE,name="actor_optimizer").minimize(self.policy_loss, var_list=get_vars('model/actor'))
        self.vf_optimizer = tf.train.AdamOptimizer(self.LEARNING_RATE,name="vf_optimizer").minimize(self.values_losses,var_list=get_vars("model/critic"))
        self.entropy_optimizer = tf.train.AdamOptimizer(learning_rate=self.LEARNING_RATE,name="entropy_optimizer").minimize(ent_coef_loss,var_list=self.log_ent_coef)
        
        self.save = save
        self.saver = tf.train.Saver(tf.global_variables())
        self.saver_path = saver_path

        if restore == True:
            self.saver.restore(self.sess, "sac_one_step.ckpt")
        else:
          self.sess.run(tf.global_variables_initializer())

    def discount_rewards(self,r):
        running_add = 0.0
        for t in range(len(r)):
            running_add += self.GAMMA * r[t]

        return running_add

    def _preproc(self):
        df = pd.read_csv(self.path)
        self.dat = df
        self.stock()
        X = self.rsi(self.dat["Close"])
        Y = np.asanyarray(self.dat[["%K","%D"]]).reshape((-1,2))
        # Z = MinMaxScaler().fit_transform(self.dat[["Close"]]) 
        X = np.asanyarray(X).reshape((-1,1))
        X = np.concatenate([X,Y],1)

        gen = tf.keras.preprocessing.sequence.TimeseriesGenerator(X, X, self.window_size)
        x = []
        y = []
        for i in gen:
            x.extend(i[0].tolist())
        x = np.asanyarray(x).reshape((-1,self.window_size,X.shape[-1]))
        self.x = x

        self.df = x[-self.STEP_SIZE::]
        self.trend = np.asanyarray(df[["Open"]])[-self.STEP_SIZE::]
    
    def stock(self):
        #Create the "L14" column in the DataFrame
        self.dat['L14'] = self.dat['Low'].rolling(window=14).min()

        #Create the "H14" column in the DataFrame
        self.dat['H14'] = self.dat['High'].rolling(window=14).max()

        #Create the "%K" column in the DataFrame
        self.dat['%K'] = 100*((self.dat['Close'] - self.dat['L14']) / (self.dat['H14'] - self.dat['L14']) )

        #Create the "%D" column in the DataFrame
        self.dat['%D'] = self.dat['%K'].rolling(window=3).mean()

    def rsi(self, price, n=14):
        ''' rsi indicator '''
        gain = (price-price.shift(1)).fillna(0) # calculate price gain with previous day, first row nan is filled with 0

        def rsiCalc(p):
            # subfunction for calculating rsi for one lookback period
            avgGain = p[p>0].sum()/n
            avgLoss = -p[p<0].sum()/n 
            rs = avgGain/avgLoss
            return 100 - 100/(1+rs)

        # run for all periods with rolling_apply
        return gain.rolling(n).apply(rsiCalc)


    def _select_action(self, state, next_state=None):
        prediction, self.init_value = self.sess.run([self.policy_out, self.last_state],
                                                      feed_dict={self.state: [state], self.initial_state: self.init_value})
        prediction = prediction[0]
        action = np.argmax(prediction)

        self.pred = prediction
        return action

    def _memorize(self, state, action, reward, new_state, dead, o):
        self.MEMORIES.append(
            (state, action, reward, new_state, dead, o))
        if len(self.MEMORIES) > self.MEMORY_SIZE:
            self.MEMORIES.popleft()

    def _construct(self,replay):
        states = np.array([a[0] for a in replay])
        new_states = np.array([a[3] for a in replay])
        init_values = np.array([a[-1] for a in replay])
        actions = np.array([a[1] for a in replay]).reshape((-1, self.OUTPUT_SIZE))
        rewards = np.array([a[2] for a in replay]).reshape((-1, 1))

        absolute_errors = self.sess.run(self.absolute_errors,
                                feed_dict={self.state:states,self.new_state: new_states, self.action: actions,
                                           self.reward: rewards,self.initial_state:init_values})
        return absolute_errors

    def prob(self):
              prob = np.asanyarray(self.history)
              a = np.mean(prob == 0)
              b = np.mean(prob == 1)
              c = 1 - (a + b)
              prob = [a,b,c]
              return prob

    def get_state(self, t):
        df = self.df[t]
        return df

    def run(self, queues, spread, pip_cost, los_cut, day_pip,iterations=10000, n=4):
        spread = spread / pip_cost
        done = False
        h_s = []
        for i in range(len(self.trend)):
            state = self.get_state(i)
            h_s.append(state)
        for i in range(iterations):
            if (i + 1) % 11 == 0:
                self.rand = np.random.RandomState()
                h = self.rand.randint(self.x.shape[0]-(self.STEP_SIZE+1))
                self.df = self.x[h:h+self.STEP_SIZE]
                self.trend = np.asanyarray(self.dat[["Open"]])[h:h+self.STEP_SIZE]

                for epock in range(len(self.trend)):
                    state = self.get_state(epock)
                    h_s.append(state)
            cost = 0
            position = 3
            pip = []
            total_pip = 0.0
            extend = pip.extend
            penalty = 0
            states = []
            h_a = []
            h_r = []
            h_i = []
            self.init_value = self.rand.randn(1, 512)
            tau = 0
            old_reword = 0.0
            old = np.asanyarray(0)
            self.history = []
            self.MEMORIES = deque()
            for t in  range(0, len(self.trend)-1):
                action = self._select_action(h_s[t])
                h_i.append(self.init_value[0])
                h_a.append(self.pred)
                self.history.append(action)
                
                states,pip,position,total_pip,penalty = self.rewards(self.trend[t],pip,action,position,states,pip_cost,spread,extend,total_pip,penalty)

                reward =  total_pip - old_reword
                old_reword = total_pip
                h_r.append(reward)

            for t in range(0, len(self.trend)-1):
                tau = t - n + 1
                if tau >= 0:
                  rewards = self.discount_rewards(h_r[tau+1:tau+n])
                  self._memorize(h_s[tau], h_a[tau], rewards*10, h_s[t+1], done, h_i[tau])

            batch_size = 250
            replay = random.sample(self.MEMORIES, batch_size)
            ae = np.asanyarray(self._construct(replay)).reshape((1,-1))
            queues.put((replay,ae))

            if (i + 1) % 10 == 0:
                self.pip = np.asanyarray(pip) * pip_cost
                self.pip = [p if p >= -los_cut else -los_cut for p in self.pip]
                self.total_pip = np.sum(self.pip)
                mean_pip = total_pip / (t + 1)
                trade_accuracy = np.mean(np.asanyarray(pip) > 0)
                self.trade = trade_accuracy
                mean_pip *= day_pip
                prob = self.prob()

                print('action probability = ', prob)
                print('trade accuracy = ', trade_accuracy)
                print('epoch: %d, total rewards: %f, mean rewards: %f' % (i + 1, float(self.total_pip), float(mean_pip)))

            time.sleep(1)
            try:
                self.saver.restore(self.sess, "sac_one_step.ckpt")
            except:
                print("not restore")
####################################################################################################################################

class Leaner:
    LEARNING_RATE = 1e-4
    GAMMA = 0.99
    STEP_SIZE = 480
    MEMORY_SIZE = 20000

    def __init__(self, path, window_size, sess,OUTPUT_SIZE=3, device='/device:GPU:0', save=False, saver_path=None, restore=False, noise=True, norm=True, ent_coef='auto', target_entropy='auto'):
        self.path = path
        self.window_size = window_size
        self.OUTPUT_SIZE = OUTPUT_SIZE
        self._preproc()
        self.state_size = (None, self.window_size, self.df.shape[-1])
        self.memory = Memory(self.MEMORY_SIZE)
        self.rewards = reward
        self.action_noise = 0.1
        self.noise_clip = 0.5
        self.act_noise = 0.4
        self.best_pip = None
        #
        self.ent_coef = ent_coef
        self.target_entropy = target_entropy
        # tf.reset_default_graph()
        self.sess = sess
        with tf.device(device):
            with tf.variable_scope("input"):
              self.policy_tf = Actor_Critic(norm,noise)
              self.target_policy = Actor_Critic(norm,noise)

              self.state = tf.placeholder(tf.float32, self.state_size)
              self.new_state = tf.placeholder(tf.float32, self.state_size)
              self.initial_state = tf.placeholder(tf.float32,(None,512))
              self.action = tf.placeholder(tf.float32,(None,self.OUTPUT_SIZE))
              self.reward = tf.placeholder(tf.float32,(None,1))

            with tf.variable_scope("model", reuse=False):
              self.tuple = self.policy_tf.actor(
                  self.state,self.initial_state,self.OUTPUT_SIZE,"actor")
              self.deterministic_action, self.policy_out, logp_pi, self.entropy, self.last_state = self.tuple[0],self.tuple[1],self.tuple[2],self.tuple[3],self.tuple[4]
              qf1, qf2, value_fn = self.policy_tf.critic(self.state, self.initial_state, self.action, create_vf=True, create_qf=True,name="critic")
              qf1_pi, qf2_pi, _ = self.policy_tf.critic(
                  self.state, self.initial_state, self.policy_out, create_vf=True, create_qf=True, name="critic")
              self.qf = qf1_pi

            if self.target_entropy == 'auto':
                # automatically set target entropy if needed
                self.target_entropy = -np.prod(self.OUTPUT_SIZE).astype(np.float32)
            else:
                # Force conversion
                # this will also throw an error for unexpected string
                self.target_entropy = float(self.target_entropy)

            if isinstance(self.ent_coef, str) and self.ent_coef.startswith('auto'):
                # Default initial value of ent_coef when learned
                init_value = 1.0
                if '_' in self.ent_coef:
                    init_value = float(self.ent_coef.split('_')[1])
                    assert init_value > 0., "The initial value of ent_coef must be greater than 0"

                self.log_ent_coef = tf.get_variable('log_ent_coef', dtype=tf.float32,
                                                    initializer=np.log(init_value).astype(np.float32))
                self.ent_coef = tf.exp(self.log_ent_coef)
            else:
                self.ent_coef = float(self.ent_coef)

            with tf.variable_scope("target", reuse=False):
                policy_out, _, _, _,_ = self.target_policy.actor(
                    self.new_state,self.initial_state,self.OUTPUT_SIZE,"actor")
                action_noise = tf.random_normal(tf.shape(policy_out), stddev=self.action_noise)
                action_noise = tf.clip_by_value(action_noise, -self.noise_clip, self.noise_clip)
                noisy_action = tf.clip_by_value(policy_out + action_noise, -1, 1)
                target_qf1,target_qf2,target_vf = self.target_policy.critic(self.new_state,self.initial_state,policy_out,create_qf=True, create_vf=True)
            with tf.variable_scope("loss"):
                min_qf_pi = tf.minimum(qf1_pi, qf2_pi)
                min_qf = tf.minimum(target_qf1, target_qf2)
                q_backup = tf.stop_gradient(
                        self.reward + self.GAMMA * target_vf
                )
                qf1_loss = tf.abs(0.5 * tf.reduce_mean((q_backup - qf1) ** 2))
                self.qf1_loss = qf1_loss
                qf2_loss = tf.abs(0.5 * tf.reduce_mean((q_backup - qf2) ** 2))

                self.absolute_errors = tf.abs(q_backup - qf1)

                ent_coef_loss = -tf.reduce_mean(self.log_ent_coef * tf.stop_gradient(logp_pi + self.target_entropy))

                policy_kl_loss = (tf.reduce_mean(self.ent_coef * logp_pi - qf1_pi))
                v_backup = tf.reduce_mean(min_qf_pi - self.ent_coef * logp_pi)
                value_loss = tf.abs(0.5 * tf.reduce_mean((value_fn - v_backup) ** 2))
                self.policy_loss = policy_kl_loss
                self.values_losses = qf1_loss + qf2_loss + value_loss

            v_p = get_vars("model/critic")
            self.policy_train_op = tf.train.AdamOptimizer(self.LEARNING_RATE,name="actor_optimizer").minimize(self.policy_loss, var_list=get_vars('model/actor'))
            self.value_optimizer = tf.train.AdamOptimizer(self.LEARNING_RATE, name="vf_optimizer").minimize(self.values_losses, var_list=v_p)
            self.entropy_optimizer = tf.train.AdamOptimizer(learning_rate=self.LEARNING_RATE,name="entropy_optimizer").minimize(ent_coef_loss,var_list=self.log_ent_coef)

        source_params = get_vars("model/")
        target_params = get_vars("target/")

        target_init_op = [
            tf.assign(target, source)
            for target, source in zip(target_params, source_params)
        ]

        self.target_ops = [
            tf.assign(target, (1 - 0.01) * target + 0.01 * source)
            for target, source in zip(target_params, source_params)
        ]

        self.save = save
        self.saver = tf.train.Saver(tf.global_variables(),max_to_keep=1, )
        self.saver_path = saver_path

        if restore == True:
          self.saver.restore(self.sess, "sac_one_step.ckpt")
        else:
          self.sess.run(tf.global_variables_initializer())
          self.sess.run(target_init_op)

    def _preproc(self):
        df = pd.read_csv(self.path)
        self.dat = df
        self.stock()
        X = self.rsi(self.dat["Close"])
        Y = np.asanyarray(self.dat[["%K", "%D"]]).reshape((-1, 2))
        # Z = MinMaxScaler().fit_transform(self.dat[["Close"]])
        X = np.asanyarray(X).reshape((-1, 1))
        X = np.concatenate([X, Y], 1)

        gen = tf.keras.preprocessing.sequence.TimeseriesGenerator(X, X, self.window_size)
        x = []
        y = []
        for i in gen:
            x.extend(i[0].tolist())
        x = np.asanyarray(x).reshape((-1,self.window_size,X.shape[-1]))
        self.x = x

        self.df = x[self.STEP_SIZE::]
        self.trend = np.asanyarray(df[["Open"]])[self.STEP_SIZE::]
    
    def stock(self):
        #Create the "L14" column in the DataFrame
        self.dat['L14'] = self.dat['Low'].rolling(window=14).min()

        #Create the "H14" column in the DataFrame
        self.dat['H14'] = self.dat['High'].rolling(window=14).max()

        #Create the "%K" column in the DataFrame
        self.dat['%K'] = 100*((self.dat['Close'] - self.dat['L14']) / (self.dat['H14'] - self.dat['L14']) )

        #Create the "%D" column in the DataFrame
        self.dat['%D'] = self.dat['%K'].rolling(window=3).mean()

    def rsi(self, price, n=14):
        ''' rsi indicator '''
        gain = (price-price.shift(1)).fillna(0) # calculate price gain with previous day, first row nan is filled with 0

        def rsiCalc(p):
            # subfunction for calculating rsi for one lookback period
            avgGain = p[p>0].sum()/n
            avgLoss = -p[p<0].sum()/n 
            rs = avgGain/avgLoss
            return 100 - 100/(1+rs)

        # run for all periods with rolling_apply
        return gain.rolling(n).apply(rsiCalc)
    
    def _construct_memories_and_train(self, replay, index=None):
        # ndaarrayにしないとなんかエラーが発生する
        replay = np.asanyarray(replay)

        states = np.array([a[0][0] for a in replay])
        new_states = np.array([a[0][3] for a in replay])
        init_values = np.array([a[0][-1] for a in replay])
        actions = np.array([a[0][1] for a in replay]).reshape((-1, self.OUTPUT_SIZE))
        rewards = np.array([a[0][2] for a in replay]).reshape((-1, 1))

        step_ops = [self.qf1_loss, self.absolute_errors,
                    self.policy_train_op]

        cost, absolute_errors, _= self.sess.run(step_ops,feed_dict={self.state: states, self.new_state: new_states,
         self.action: actions,self.reward: rewards, self.initial_state: init_values})
        _,_ = self.sess.run([self.value_optimizer, self.entropy_optimizer], feed_dict={self.state: states, self.new_state: new_states,
                                                                                     self.action: actions, self.reward: rewards, self.initial_state: init_values})
        self.sess.run(self.target_ops)
        
        print("td error: ", cost)
        if index is None:
          self.memory.batch_update(self.tree_idx, absolute_errors)
        else:
          self.memory.batch_update(index, absolute_errors)

        return cost

    def leaner(self, queues,files, iterations=10000000):
        i = 0
        a = True
        # 経験再生バッファにデータが入力されるまでループをする。
        while a:
            if not queues.empty():
                replay, ae = queues.get()
                for r in range(len(replay)):
                    exp = replay[r]
                    self.memory.store(exp, ae[0, r])
                a = False

        for _ in range(iterations):
            size = 32
            try:
                self.tree_idx, batch = self.memory.sample(size)
                cost = self._construct_memories_and_train(batch)
                i += 1
                saved_path = self.saver.save(self.sess, self.saver_path,write_meta_graph=False)
                # google colabでgoogle driveを使うことを前提にしている
                # tensorflowは上書きではなく前のファイルのを削除して新しくセーブするため、driveの容量がすぐにいっぱいになってしまう
                # そのため、継続的なトレーニングができなくなってしまう。
                if (i + 1) % 10 == 0:
                    _ = shutil.copy("/content/", + self.saver_path + ".data-00000-of-00001","/content/drive/My Drive")
                    _ = shutil.copy("/content/", + self.saver_path + ".index","/content/drive/My Drive")
                    _ = shutil.copy("/content/checkpoint","/content/drive/My Drive")
            except:
                # pass
                import traceback
                traceback.print_exc()

            if not queues.empty():
                replay,ae = queues.get()
                for r in range(len(replay)):
                    exp = replay[r]
                    self.memory.store(exp, ae[0, r])
            time.sleep(0.1)

