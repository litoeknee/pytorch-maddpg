#!/usr/bin/env python
import os, sys

sys.path.insert(1, os.path.join(sys.path[0], '..'))
import argparse
from torch.autograd import Variable
# from madrl_environments.pursuit import MAWaterWorld_mod
from multiagent.environment import MultiAgentEnv
# from multiagent.policy import InteractivePolicy
import multiagent.scenarios as scenarios
from MADDPG import MADDPG
import numpy as np
import torch as th
import visdom

# from params import scale_reward

# do not render the scene
e_render = False

parser = argparse.ArgumentParser(description=None)
parser.add_argument('-s', '--scenario', default='', help='Path of the scenario Python script.')
args = parser.parse_args()

# load scenario from script
scenario = scenarios.load(args.scenario).Scenario()
# create world
world = scenario.make_world()
# create multiagent environment
env = MultiAgentEnv(world, scenario.reset_world, scenario.reward, scenario.observation, info_callback=None,
                    done_callback=scenario.done, shared_viewer=True, discrete_action_space=False)

# food_reward = 10.
# poison_reward = -1.
# encounter_reward = 0.01
# n_coop = 2
# world = MAWaterWorld_mod(n_pursuers=2, n_evaders=50,
#                          n_poison=50, obstacle_radius=0.04,
#                          food_reward=food_reward,
#                          poison_reward=poison_reward,
#                          encounter_reward=encounter_reward,
#                          n_coop=n_coop,
#                          sensor_range=0.2, obstacle_loc=None, )

# vis = visdom.Visdom(port=8097)
vis = visdom.Visdom()
reward_record = []

np.random.seed(1234)
th.manual_seed(1234)
# world.seed(1234)
# n_agents = world.n_pursuers
# n_states = 213
# n_actions = 2
n_agents = env.n
# Currently supports homogenious agents
n_states = env.observation_space[0].shape[0]
n_actions = env.action_space[0].shape[0]
print(env.action_space[0].shape[0], n_states)
capacity = 1000000
batch_size = 1000

n_episode = 20000
max_steps = 100
episodes_before_train = 100

win = None
param = None

maddpg = MADDPG(n_agents, n_states, n_actions, batch_size, capacity,
                episodes_before_train)

FloatTensor = th.cuda.FloatTensor if maddpg.use_cuda else th.FloatTensor
for i_episode in range(n_episode):
    # obs = world.reset()
    obs = env.reset()
    obs = np.stack(obs)
    if isinstance(obs, np.ndarray):
        obs = th.from_numpy(obs).float()
    total_reward = 0.0
    rr = np.zeros((n_agents,))
    t = 0
    for t in range(max_steps):
        # render every 100 episodes to speed up training
        if i_episode % 100 == 0 and e_render:
            # world.render()
            env.render()
        # env.render()
        obs = Variable(obs).type(FloatTensor)
        action = maddpg.select_action(obs).data.cpu()
        # print(action)
        # obs_, reward, done, _ = world.step(action.numpy())
        obs_, reward, done, _ = env.step(action.numpy())

        reward = th.FloatTensor(reward).type(FloatTensor)
        obs_ = np.stack(obs_)
        obs_ = th.from_numpy(obs_).float()
        if t != max_steps - 1:
            next_obs = obs_
        else:
            next_obs = None

        total_reward += reward.sum()
        rr += reward.cpu().numpy()
        maddpg.memory.push(obs.data, action, next_obs, reward)
        obs = next_obs

        c_loss, a_loss = maddpg.update_policy()
        # print(done)
        # To prevent agents from out-of-bound

        # input("raw_input: ")
        if np.any(done):
            break
    total_reward /= t
    rr /= t

    maddpg.episode_done += 1
    print('Episode: %d, reward = %f' % (i_episode, total_reward))
    reward_record.append(total_reward)

    if maddpg.episode_done == maddpg.episodes_before_train:
        print('training now begins...')
        print('MADDPG with CLEAN reward\n' +
              'agent=%d' % n_agents)
        # print('MADDPG on WaterWorld\n' +
        #       'scale_reward=%f\n' % scale_reward +
        #       'agent=%d' % n_agents +
        #       ', coop=%d' % n_coop +
        #       ' \nlr=0.001, 0.0001, sensor_range=0.3\n' +
        #       'food=%f, poison=%f, encounter=%f' % (
        #           food_reward,
        #           poison_reward,
        #           encounter_reward))

    if win is None:
        win = vis.line(X=np.arange(i_episode, i_episode + 1),
                       Y=np.array([
                           np.append(total_reward, rr)]),
                       opts=dict(
                           ylabel='Reward',
                           xlabel='Episode',
                           title='MADDPG with CLEAN reward\n' +
                                 'agent=%d' % n_agents,
                           # 'MADDPG on WaterWorld_mod\n' +
                           #  'agent=%d' % n_agents +
                           #  ', coop=%d' % n_coop +
                           #  ', sensor_range=0.2\n' +
                           #  'food=%f, poison=%f, encounter=%f' % (
                           #      food_reward,
                           #      poison_reward,
                           #      encounter_reward),
                           legend=['Total'] +
                                  ['Agent-%d' % i for i in range(n_agents)]))
    else:
        vis.line(X=np.array(
            [np.array(i_episode).repeat(n_agents + 1)]),
            Y=np.array([np.append(total_reward,
                                  rr)]),
            win=win,
            update='append')
    if param is None:
        param = vis.line(X=np.arange(i_episode, i_episode + 1),
                         Y=np.array([maddpg.var[0]]),
                         opts=dict(
                             ylabel='Var',
                             xlabel='Episode',
                             title='MADDPG on Simple Spread: Exploration',
                             legend=['Variance']))
    else:
        vis.line(X=np.array([i_episode]),
                 Y=np.array([maddpg.var[0]]),
                 win=param,
                 update='append')

# world.close()
