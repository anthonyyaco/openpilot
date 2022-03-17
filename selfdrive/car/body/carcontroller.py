import numpy as np
from selfdrive.car.body import bodycan
from opendbc.can.packer import CANPacker


class CarController():
  def __init__(self, dbc_name, CP, VM):
    self.CP = CP
    self.car_fingerprint = CP.carFingerprint

    self.lkas_max_torque = 0
    self.last_angle = 0

    self.packer = CANPacker(dbc_name)
    # ////////////////////////////////
    self.i_speed = 0

    self.i_balance = 0
    self.d_balance = 0

    self.i_torque = 0

    self.speed_measured = 0.
    self.speed_desired = 0.

    self.torque_r_filtered = 0.
    self.torque_l_filtered = 0.
    # ////////////////////////////////

  @staticmethod
  def deadband_filter(torque, deadband):
      if torque > 0:
        torque += deadband
      else:
        torque -= deadband
      return torque

  def update(self, c, CS, frame, actuators, cruise_cancel, hud_alert,
             left_line, right_line, left_lane_depart, right_lane_depart):

    # ///////////////////////////////////////
    # Setpoint speed PID
    kp_speed = 0.001
    ki_speed = 0
    alpha_speed = 1.0

    self.speed_measured = (CS.out.wheelSpeeds.fl + CS.out.wheelSpeeds.fr) / 2.
    self.speed_desired = (1. - alpha_speed)*self.speed_desired
    p_speed = (self.speed_desired - self.speed_measured)
    self.i_speed += ki_speed * p_speed
    self.i_speed = np.clip(self.i_speed, -0.1, 0.1)
    set_point = p_speed * kp_speed + self.i_speed

    # Balancing PID
    kp_balance = 1300
    ki_balance = 0
    kd_balance = 280
    alpha_d_balance = 1.0

    p_balance = (-c.orientationNED[1]) - set_point
    self.i_balance += CS.out.wheelSpeeds.fl + CS.out.wheelSpeeds.fr
    self.d_balance =  np.clip(((1. - alpha_d_balance) * self.d_balance + alpha_d_balance * -c.angularVelocity[1]), -1., 1.)
    torque = int(np.clip((p_balance*kp_balance + self.i_balance*ki_balance + self.d_balance*kd_balance), -1000, 1000))

    # Positional recovery PID
    kp_torque = 0.95
    ki_torque = 0.1

    p_torque = (CS.out.wheelSpeeds.fl - CS.out.wheelSpeeds.fr)
    self.i_torque += (CS.out.wheelSpeeds.fl - CS.out.wheelSpeeds.fr)
    torque_diff = int(np.clip(p_torque*kp_torque + self.i_torque*ki_torque, -100, 100))

    # Combine 2 PIDs outputs
    torque_r = torque + torque_diff
    torque_l = torque - torque_diff

    #Low pass filter
    alpha_torque = 1.
    self.torque_r_filtered = (1. - alpha_torque) * self.torque_r_filtered + alpha_torque * self.deadband_filter(torque_r, 10)
    self.torque_l_filtered = (1. - alpha_torque) * self.torque_l_filtered + alpha_torque * self.deadband_filter(torque_l, 10)
    torque_r = int(np.clip(self.torque_r_filtered, -1000, 1000))
    torque_l = int(np.clip(self.torque_l_filtered, -1000, 1000))
    # ///////////////////////////////////////
    can_sends = []

    apply_angle = actuators.steeringAngleDeg

    can_sends.append(bodycan.create_control(self.packer, torque_l, torque_r))

    new_actuators = actuators.copy()
    new_actuators.steeringAngleDeg = apply_angle

    return new_actuators, can_sends