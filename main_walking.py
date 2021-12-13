# This script tries to follow trajectories previously generated by a trajectory optimization algorithm
# It doesn't work :'(

#####################
#  LOADING MODULES ##
#####################

import time

import pybullet as p
import pinocchio as pin
import numpy as np
from numpy.linalg import inv, pinv
from numpy import nan

from utils.robot_wrapper import RobotWrapper
from utils.robot_simulator import RobotSimulator
from tsid_quadruped import TsidQuadruped
import conf as conf

import matplotlib.pyplot as plt

# Functions to initialize the simulation and retrieve joints positions/velocities
from utils.initialization_simulation import configure_simulation, getPosVelJoints

####################
#  INITIALIZATION ##
####################
data = np.load(conf.DATA_FILE_TSID)


dt = conf.dt # time step of the simulation
t = 0.0
N = data['com'].shape[1]
N_pre = conf.N_pre
N_post = conf.N_post

# Load trajectories

com_pos = np.empty((3, N+N_post))*nan
com_vel = np.empty((3, N+N_post))*nan
com_acc = np.empty((3, N+N_post))*nan
x_LF   = np.empty((3, N+N_post))*nan
dx_LF  = np.empty((3, N+N_post))*nan
ddx_LF = np.empty((3, N+N_post))*nan
ddx_LF_des = np.empty((3, N+N_post))*nan
x_RF   = np.empty((3, N+N_post))*nan
dx_RF  = np.empty((3, N+N_post))*nan
ddx_RF = np.empty((3, N+N_post))*nan
ddx_RF_des = np.empty((3, N+N_post))*nan
f_RF = np.zeros((6, N+N_post))
f_LF = np.zeros((6, N+N_post))
cop_RF = np.zeros((2, N+N_post))
cop_LF = np.zeros((2, N+N_post))

contact_phase = data['contact_phase']
com_pos_ref = np.asarray(data['com'])
com_vel_ref = np.asarray(data['dcom'])
com_acc_ref = np.asarray(data['ddcom'])

x_FL_ref    = np.asarray(data['x_FL'])
dx_FL_ref   = np.asarray(data['dx_FL'])
ddx_FL_ref  = np.asarray(data['ddx_FL'])

x_FR_ref    = np.asarray(data['x_FR'])
dx_FR_ref   = np.asarray(data['dx_FR'])
ddx_FR_ref  = np.asarray(data['ddx_FR'])

x_HL_ref    = np.asarray(data['x_HL'])
dx_HL_ref   = np.asarray(data['dx_HL'])
ddx_HL_ref  = np.asarray(data['ddx_HL'])

x_HR_ref    = np.asarray(data['x_HR'])
dx_HR_ref   = np.asarray(data['dx_HR'])
ddx_HR_ref  = np.asarray(data['ddx_HR'])

cop_ref     = np.asarray(data['cop'])
com_acc_des = np.empty((3, N+N_post))*nan # acc_des = acc_ref - Kp*pos_err - Kd*vel_err

# If True then we will sleep in the main loop to have a 1:1 ratio of (elapsed real time / elapsed time in the
# simulation)

startup_pos  = np.concatenate((np.insert(com_pos_ref[0:2, 0], 2, 0.335), np.zeros(16)))
realTimeSimulation = True
enableGUI = True  # enable PyBullet GUI or not

q0 = np.zeros(19)
q0[0:3] = np.insert(com_pos_ref[0:2, 0], 2, 0.5)

startup_pos  = np.concatenate((np.insert(com_pos_ref[0:2, 0], 2, 0.335), np.pi*np.ones(16)))
realTimeSimulation = True
enableGUI = True  # enable PyBullet GUI or not

robotId, r, revoluteJointIndices = configure_simulation(dt, q0[:3], enableGUI)
robot = RobotWrapper(r.model, r.collision_model, r.visual_model)

q0 = getPosVelJoints(robotId, revoluteJointIndices)[0]

# TSID implementation for quadrupeds
tsid = TsidQuadruped(conf, q0)

x_rf   = tsid.get_HR_pos()
offset = x_rf - x_HR_ref[:,0]
for i in range(N):
    com_pos_ref[:,i] += offset + np.array([0.,0.,0.0])
    x_FL_ref[:,i] += offset
    x_FR_ref[:,i] += offset
    x_HL_ref[:,i] += offset
    x_HR_ref[:,i] += offset
    
tau    = np.zeros((tsid.robot.na, N+N_post))
q_log  = np.zeros((tsid.robot.nq, N+N_post))
v_log  = np.zeros((tsid.robot.nv, N+N_post))

x_HR_log = np.zeros((3, N+N_post))
com_log  = np.zeros((3, N+N_post))
com_ref_log  = np.zeros((3, N+N_post))
FL_force_log = np.zeros((3, N+N_post))
FR_force_log = np.zeros((3, N+N_post))
HL_force_log = np.zeros((3, N+N_post))
HR_force_log = np.zeros((3, N+N_post))

FR_ref_log = np.zeros((3, N+N_post))

# Balls to show trajectories
def build_sphere(x0, r, color):
    viz = p.createVisualShape(p.GEOM_SPHERE,
                                radius = r,
                                rgbaColor = color)
    sph = p.createMultiBody(
              baseMass = 0,
              baseVisualShapeIndex= viz, 
              basePosition = x0,
              useMaximalCoordinates=True)
    return(sph)

red_color = (1,1,0,1)
radius = 0.02
ref_sphere1 = build_sphere(conf.x0, radius, red_color)
ref_sphere2 = build_sphere(conf.x0, radius, red_color)
ref_sphere3 = build_sphere(conf.x0, radius, red_color)
ref_sphere4 = build_sphere(conf.x0, radius, red_color)
ref_sphere5 = build_sphere(conf.x0, radius, red_color)
com_sphere = build_sphere(conf.x0, radius, (0,0,1,1))

# Now I'm only tracking a sine wave with the CoM, 
# This will became a trajectory from the trajectory optimization, along with trajectories for feet
offset     = tsid.robot.com(tsid.formulation.data()) + np.array([0.0, 0.0, -0.0])
amp        = np.array([0.05, 0.0, 0.03])
two_pi_f             = 2*np.pi*np.array([1, 1.0, 0.8])
two_pi_f_amp         = np.multiply(two_pi_f,amp)
two_pi_f_squared_amp = np.multiply(two_pi_f, two_pi_f_amp)


q, qdot = tsid.q, tsid.qdot

###############
#  MAIN LOOP ##
###############

for i in range(-N_pre, N + N_post):
    # Time at the start of the loop
    if realTimeSimulation:
        t0 = time.time()
    
    # Position and velocity of the PyBullet simulator
    q, qdot = getPosVelJoints(robotId, revoluteJointIndices)
    
    if i == 0:
        print("Removing contact from FR, HL")
        tsid.remove_contact_FR()
        tsid.remove_contact_HL()
    elif i>0 and i< N - 1:
        if contact_phase[i] != contact_phase[i-1]:
            #print("Time %.3f Changing contact phase from %s to %s"%(t, contact_phase[i-1], contact_phase[i]))
            if contact_phase[i] == 'right':
                tsid.add_contact_FL()
                tsid.add_contact_HR()
                tsid.remove_contact_FR()
                tsid.remove_contact_HL()
            else:
                print("Hind Left in contact")
                tsid.add_contact_FR()
                tsid.add_contact_HL()
                tsid.remove_contact_FL()
                tsid.remove_contact_HR()
                
    if i<0:
        com_log[:, i] = tsid.robot.com(tsid.formulation.data())
        com_ref_log[:, i] = com_pos_ref[:, 0]
        
        tsid.set_com_ref(com_pos_ref[:,0], 0*com_vel_ref[:,0], 0*com_acc_ref[:,0])
        #tsid.set_com_ref(offset + np.multiply(amp, np.sin(two_pi_f*t)), np.multiply(two_pi_f_amp, np.cos(two_pi_f*t)), np.multiply(two_pi_f_squared_amp, -np.sin(two_pi_f*t)))
        #com_ref_log[:, i] = offset + np.multiply(amp, np.sin(two_pi_f*t))
        
        p.resetBasePositionAndOrientation(ref_sphere1, com_ref_log[:, 0], p.getQuaternionFromEuler([0,0,0]))
        p.resetBasePositionAndOrientation(ref_sphere2, x_FL_ref[:, 0], p.getQuaternionFromEuler([0,0,0]))
        p.resetBasePositionAndOrientation(ref_sphere3, x_FR_ref[:, 0], p.getQuaternionFromEuler([0,0,0]))
        p.resetBasePositionAndOrientation(ref_sphere4, x_HL_ref[:, 0], p.getQuaternionFromEuler([0,0,0]))
        p.resetBasePositionAndOrientation(ref_sphere5, x_HR_ref[:, 0], p.getQuaternionFromEuler([0,0,0]))
        p.resetBasePositionAndOrientation(com_sphere, com_log[:, i], p.getQuaternionFromEuler([0,0,0]))
        
    elif i<N-1:
        #tsid.set_com_ref(com_pos_ref[:,0], 0*com_vel_ref[:,0], 0*com_acc_ref[:,0])
        tsid.set_com_ref(com_pos_ref[:,i], com_vel_ref[:,i], com_acc_ref[:,i])
        com_ref_log[:, i] = com_pos_ref[:, i]
        
        tsid.set_FL_ref(x_FL_ref[:,i], dx_FL_ref[:, i], ddx_FL_ref[:, i])
        tsid.set_HR_ref(x_HR_ref[:,i], dx_HR_ref[:, i], ddx_HR_ref[:, i])        
        tsid.set_FR_ref(x_FR_ref[:,i], dx_FR_ref[:, i], ddx_FR_ref[:, i])
        tsid.set_HL_ref(x_HL_ref[:,i], dx_HL_ref[:, i], ddx_HL_ref[:, i])
        
        com_log[:, i] = tsid.robot.com(tsid.formulation.data())
        p.resetBasePositionAndOrientation(ref_sphere1, com_pos_ref[:, i], p.getQuaternionFromEuler([0,0,0]))
        p.resetBasePositionAndOrientation(ref_sphere2, x_FL_ref[:, i], p.getQuaternionFromEuler([0,0,0]))
        p.resetBasePositionAndOrientation(ref_sphere3, x_FR_ref[:, i], p.getQuaternionFromEuler([0,0,0]))
        p.resetBasePositionAndOrientation(ref_sphere4, x_HL_ref[:, i], p.getQuaternionFromEuler([0,0,0]))
        p.resetBasePositionAndOrientation(ref_sphere5, x_HR_ref[:, i], p.getQuaternionFromEuler([0,0,0]))
        p.resetBasePositionAndOrientation(com_sphere, com_log[:, i], p.getQuaternionFromEuler([0,0,0]))

        tau[:, i] = jointTorques
        x_HR_log[:, i] = tsid.get_HR_pos()
        com_log[:, i] = tsid.robot.com(tsid.data)
    
    
    HQPData = tsid.formulation.computeProblemData(t, q, qdot)
    if i == 0: HQPData.print_all()

    sol = tsid.solver.solve(HQPData)
    if(sol.status!=0):
        print("[%d] QP problem could not be solved! Error code:"%(i), sol.status)
        break
    
    q2dot = tsid.formulation.getAccelerations(sol)
    jointTorques = tsid.formulation.getActuatorForces(sol)
    
    # Set control torques for all joints in PyBullet
    p.setJointMotorControlArray(robotId, revoluteJointIndices, controlMode=p.TORQUE_CONTROL, forces=jointTorques)

    # Compute one step of simulation
    p.stepSimulation()
    t += dt
    # Sleep to get a real time simulation
    if realTimeSimulation:
        t_sleep = dt - (time.time() - t0)
        if t_sleep > 0:
            time.sleep(t_sleep)
            
print("Finished :)")
            
# Shut down the PyBullet client
#p.disconnect()


'''for i in range (3):
    plt.plot(x_HR_log[i, :])
    plt.plot(x_HR_ref[i, :])
    #plt.ylim([-0.1,0.5])
    plt.legend(['Performed', 'Desired'])
    plt.show()'''

for i in range (3):
    plt.title('COM_x'+str(i))
    plt.plot(com_log[i, :])
    plt.plot(com_ref_log[i, :])
    #plt.ylim([-0.1,0.5])
    plt.legend(['Performed', 'Desired'])
    plt.show()
    
'''for i in range(3):
    plt.plot(FR_force_log[i, :])
    plt.plot(HL_force_log[i, :])
    plt.show()'''