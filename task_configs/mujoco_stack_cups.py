from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool

import torch
from policies.common.maker import post_init_policies
from task_configs.template import (
    get_task_name,
    replace_task_name,
    set_paths,
    activator,
    TASK_CONFIG_DEFAULT,
)


def policy_maker(config:dict, stage=None):
    from policies.act.act import ACTPolicy
    from policies.traditionnal.cnnmlp import CNNMLPPolicy
    # from policies.diffusion.diffusion_policy import DiffusionPolicy
    with torch.inference_mode():#禁用梯度计算
        policy = ACTPolicy(config)
        post_init_policies([policy], stage, [config["ckpt_path"]])

        if "ckpt_path_1" in config:
            policy_1 = CNNMLPPolicy(config)
            post_init_policies([policy_1], stage, [config["ckpt_path_1"]])
    
        if stage == "train":
            return policy

        elif stage == "eval":
            if TASK_CONFIG_DEFAULT["eval"]["ensemble"] == None:
                return policy
            else:
                ckpt_path = config["ckpt_path"]
                assert ckpt_path is not None, "ckpt_path must exist for loading policy"
                # TODO: all policies should load the ckpt (policy maker should return a class)

                policy.cuda()
                policy.eval()
                policy_1.cuda()
                policy_1.eval()


                # def ensemble_policy(*args, **kwargs):
                #     #TODO：转换为并行操作
                #     actions = policy(*args, **kwargs)
                #     actions_2 = policy_1(*args, **kwargs)
                #     # average the actions
                #     actions = (actions + actions_2) / 2
                #     return actions
                
                def run_policy(policy, *args, **kwargs):
                    with torch.inference_mode():
                        a_hat = policy(*args, **kwargs)
                        a_hat = a_hat.clone()  # 在更新之前克隆
                        return policy.temporal_ensembler.update(a_hat)

                def ensemble_policy(*args, **kwargs):
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        future_policy = executor.submit(run_policy, policy, *args, **kwargs)
                        
                        future_policy_1 = executor.submit(run_policy, policy_1, *args, **kwargs)

                        actions = future_policy.result()
                        actions_2 = future_policy_1.result()

                    # average the actions
                    actions = (actions + actions_2) / 2
                    return actions
                
                # 定义 reset 方法
                def reset():
                    if hasattr(policy, "reset"):
                        policy.reset()
                    if hasattr(policy_1, "reset"):
                        policy_1.reset()

                # 将 reset 方法绑定到 ensemble_policy 函数上
                ensemble_policy.reset = reset

                return ensemble_policy

def environment_maker(config:dict):
    from envs.make_env import make_environment
    env_config = config["environments"]
    # TODO: use env_config only
    return make_environment(config)

@activator(False)
def augment_images(image):
    from task_configs.config_augmentation.image.basic import color_transforms_1
    return color_transforms_1(image)

# auto replace the task name in the default paths accoring to the file name
TASK_NAME = get_task_name(__file__)
replace_task_name(TASK_NAME, stats_name="dataset_stats.pkl", time_stamp="now")
# but we also show how to set the whole paths manually
# DATA_DIR = f"./data/hdf5/{TASK_NAME}"
# CKPT_DIR = f"./my_ckpt/{TASK_NAME}/ckpt"
# STATS_PATH = f"./my_ckpt/{TASK_NAME}/dataset_stats.pkl"
# set_paths(DATA_DIR, CKPT_DIR, STATS_PATH)  # replace the default data and ckpt paths

chunk_size = 25
joint_num = 7
TASK_CONFIG_DEFAULT["common"]["camera_names"] = ["0"]
TASK_CONFIG_DEFAULT["common"]["state_dim"] = joint_num
TASK_CONFIG_DEFAULT["common"]["action_dim"] = joint_num
TASK_CONFIG_DEFAULT["common"]["policy_config"]["temporal_agg"] = True
TASK_CONFIG_DEFAULT["common"]["policy_config"]["chunk_size"] = chunk_size
TASK_CONFIG_DEFAULT["common"]["policy_config"]["num_queries"] = chunk_size
TASK_CONFIG_DEFAULT["common"]["policy_config"]["kl_weight"] = 10
TASK_CONFIG_DEFAULT["common"]["policy_config"]["policy_maker"] = policy_maker

TASK_CONFIG_DEFAULT["train"]["num_episodes"] = "ALL"
TASK_CONFIG_DEFAULT["train"]["num_epochs"] = 8000
TASK_CONFIG_DEFAULT["train"]["batch_size"] = 16
TASK_CONFIG_DEFAULT["train"]["learning_rate"] = 2e-5
TASK_CONFIG_DEFAULT["train"]["pretrain_ckpt_path"] = ""
TASK_CONFIG_DEFAULT["train"]["pretrain_epoch_base"] = "AUTO"

TASK_CONFIG_DEFAULT["eval"]["robot_num"] = 1
TASK_CONFIG_DEFAULT["eval"]["joint_num"] = joint_num
TASK_CONFIG_DEFAULT["eval"]["start_joint"] = "AUTO"
TASK_CONFIG_DEFAULT["eval"]["max_timesteps"] = 100
TASK_CONFIG_DEFAULT["eval"]["ensemble"] = True
TASK_CONFIG_DEFAULT["eval"]["environments"]["environment_maker"] = environment_maker

# final config
TASK_CONFIG = TASK_CONFIG_DEFAULT
