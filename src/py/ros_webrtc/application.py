"""
"""
import functools
import weakref

import rospy

from ros_webrtc.peer_connection import (
    RTCPeerConnection,
    RTCPeerConnectionCallbacks,
)


class ApplicationRTCPeerConnectionCallbacks(RTCPeerConnectionCallbacks):

    def __init__(self, app, pc):
        self.app = weakref.proxy(app)
        super(ApplicationRTCPeerConnectionCallbacks, self).__init__(pc)

    def on_data_channel(self, req):
        if not self.app.on_pc_data_channel(self.pc, req.data_channel):
            return
        return super(ApplicationRTCPeerConnectionCallbacks, self).on_data_channel(req)

    def on_ice_candidate(self, req):
        self.app.on_pc_ice_candidate(self.pc, req.candidate)
        return super(ApplicationRTCPeerConnectionCallbacks, self).on_ice_candidate(req)

    def on_ice_candidate_state_change(self, req):
        self.app.on_pc_ice_candidate_state_change(self.pc, req)
        return super(ApplicationRTCPeerConnectionCallbacks, self).on_ice_candidate_state_change(req)

    def on_signaling_state_change(self, req):
        self.app.on_pc_signaling_state_change(self.pc, req)
        return super(ApplicationRTCPeerConnectionCallbacks, self).on_signaling_state_change(req)

    def on_negotiation_needed(self, req):
        self.app.on_pc_negotiation_needed(self.pc, req)
        return super(ApplicationRTCPeerConnectionCallbacks, self).on_negotiation_needed(req)

    def on_add_stream(self, req):
        self.app.on_pc_add_stream(self.pc, req.stream)
        return super(ApplicationRTCPeerConnectionCallbacks, self).on_add_stream(req)

    def on_remove_stream(self, req):
        self.app.on_pc_remove_stream(self.pc, req.stream)
        return super(ApplicationRTCPeerConnectionCallbacks, self).on_remove_stream(req)

    def on_set_session_description(self, req):
        self.app.on_pc_set_session_description(self.pc, req)
        return super(ApplicationRTCPeerConnectionCallbacks, self).on_set_session_description(req)


class ApplicationRTCPeerConnection(RTCPeerConnection):

    def __init__(
            self,
            app,
            session_id,
            peer_id,
            bond_timeout=None,
            **kwargs):
        super(ApplicationRTCPeerConnection, self).__init__(
            session_id, peer_id, **kwargs
        )
        self.app = weakref.proxy(app)
        if bond_timeout != 0:
            self.pc_bond = self.bond(
                on_broken=self.on_pc_bond_broken,
                on_formed=self.on_pc_bond_formed,
            )
        else:
            rospy.loginfo('%s bonding disabled', self)
            self.pc_bond = None
        if self.pc_bond and bond_timeout is not None:
            self.pc_bond.heartbeat_timeout = bond_timeout
        self.rosbridge_bonds = []
        self.deleting = False
        self.callbacks = ApplicationRTCPeerConnectionCallbacks(app, self)
        self.app.pcs[(self.session_id, self.peer_id)] = self
        if self.pc_bond:
            self.pc_bond.start()

    def delete(self):
        if self.app is None:
            return
        self.app, app = None, self.app
        try:
            app.on_pc_delete(self)
        finally:
            try:
                if self.pc_bond:
                    self.pc_bond.shutdown()
                    self.pc_bond = None
                for bond in self.rosbridge_bonds:
                    bond.shutdown()
                del self.rosbridge_bonds[:]
                if self.callbacks:
                    self.callbacks.shutdown()
                try:
                    self.close()
                except rospy.ServiceException, ex:
                    rospy.loginfo('%s close cmd failed - %s', self, ex)
            finally:
                app.pcs.pop((self.session_id, self.peer_id), None)
                self.deleting = False

    def on_pc_bond_broken(self):
        rospy.loginfo('%s bond broken, deleting pc ...', self)
        self.delete()

    def on_pc_bond_formed(self):
        rospy.loginfo('%s bond formed', self)

    def on_rosbridge_bond_broken(self, label):
        rospy.loginfo('%s rosbridge "%s" bond broken, deleting pc ...', self, label)
        self.delete()

    def on_rosbridge_bond_formed(self, label):
        rospy.loginfo('%s rosbridge "%s" bond formed', self, label)

    # RTCPeerConnection

    def rosbridge(
            self,
            data_channel_label,
            launch,
            timeout=5.0,
            heartbeat=None,
            **kwargs):
        rosbridge_bond = super(ApplicationRTCPeerConnection, self).rosbridge(
            data_channel_label,
            launch,
            timeout=timeout,
            heartbeat=heartbeat,
            on_broken=functools.partial(
                self.on_rosbridge_bond_broken, data_channel_label
            ),
            on_formed=functools.partial(
                self.on_rosbridge_bond_formed, data_channel_label
            ),
            **kwargs
        )
        if not rosbridge_bond:
            return
        self.rosbridge_bonds.append(rosbridge_bond)
        return rosbridge_bond


class Application(object):

    def __init__(self, id_, ros_webrtc_namespace=None, pc_timeout=None):
        self.id = id_
        self.pcs = {}
        self.svrs = []
        self.ros_webrtc_namespace = ros_webrtc_namespace
        self.pc_timeout = pc_timeout

    def shutdown(self):
        for pc in self.pcs.values():
            pc.delete()
        for srv in self.svrs:
            srv.shutdown()

    def create_pc(self, session_id, peer_id, **kwargs):
        key = (session_id, peer_id)
        pc = self.pcs.pop(key, None)
        if pc:
            rospy.loginfo('pc %s already exists, deleting ... ', pc)
            pc.delete()
        if self.ros_webrtc_namespace:
            kwargs['namespace'] = self.ros_webrtc_namespace
        pc = ApplicationRTCPeerConnection(
            self,
            session_id,
            peer_id,
            bond_timeout=self.pc_timeout,
            **kwargs
        )
        rospy.loginfo('created pc %s', pc)
        return pc

    def delete_pc(self, session_id, peer_id):
        key = (session_id, peer_id)
        pc = self.pcs.pop(key, None)
        if pc:
            pc.delete()

    def on_pc_delete(self, pc):
        pass

    def on_pc_data_channel(self, pc, msg):
        pass

    def on_pc_negotiation_needed(self, pc, msg):
        pass

    def on_pc_ice_candidate(self, pc, msg):
        pass

    def on_pc_ice_candidate_state_change(self, pc, msg):
        pass

    def on_pc_signaling_state_change(self, pc, msg):
        pass

    def on_pc_add_stream(self, pc, msg):
        pass

    def on_pc_set_session_description(self, pc, msg):
        pass