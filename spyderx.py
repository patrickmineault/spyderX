import os
import usb.core
import usb.util
import usb.backend.libusb1
import struct
import time
import numpy as np

# Replace with the correct path to your libusb library
LIBUSB_PATH = "/opt/homebrew/Cellar/libusb/1.0.27/lib/libusb-1.0.0.dylib"


"""
SpyderX class for interfacing with the SpyderX colorimeter.

Adapted from: https://github.com/yangzhangpsy/PsyCalibrator/blob/main/PsyCalibrator/spyderX.m

Translated from Matlab to Python via Claude 3.5 Sonnet
"""
class SpyderX:
    def __init__(self):
        self.dev = None
        self.spyderData = {}
        self.backend = usb.backend.libusb1.get_backend(find_library=lambda x: LIBUSB_PATH)
        if self.backend is None:
            raise ValueError("Libusb backend not found. Check if the path is correct.")

    def initialize(self):
        try:
            self.dev = usb.core.find(idVendor=0x085C, idProduct=0x0A00, backend=self.backend)
            if self.dev is None:
                print("SpyderX device not found. Is it plugged in?")
                return False

            # Try to set configuration
            try:
                self.dev.set_configuration()
            except usb.core.USBError as e:
                print(f"Error setting configuration: {e}")

            # Try to claim interface
            try:
                if self.dev.is_kernel_driver_active(0):
                    self.dev.detach_kernel_driver(0)
                self.dev.claim_interface(0)
            except AttributeError:
                print("Warning: claim_interface not available. Continuing without it.")
            except usb.core.USBError as e:
                print(f"Error claiming interface: {e}")

            self._control_transfer(0x02, 1, 0, 1, None)
            self._control_transfer(0x02, 1, 0, 129, None)
            self._control_transfer(0x41, 2, 2, 0, None)

            self._get_hardware_version()
            self._get_serial_number()
            self._get_factory_calibration()
            self._get_amb_measure()
            self._setup_measurement()

            self.spyderData['isOpen'] = True
            return True
        except usb.core.USBError as e:
            print(f"USB error occurred: {str(e)}")
            return False

    def _control_transfer(self, bmRequestType, bRequest, wValue, wIndex, data_or_wLength):
        return self.dev.ctrl_transfer(bmRequestType, bRequest, wValue, wIndex, data_or_wLength)

    def _bulk_transfer(self, cmd, outSize):
        self.dev.write(1, cmd)
        return self.dev.read(0x81, outSize)

    def _get_hardware_version(self):
        out = self._bulk_transfer([0xd9, 0x42, 0x33, 0x00, 0x00], 28)
        self.spyderData['HWvn'] = out[5:9].tobytes().decode()

    def _get_serial_number(self):
        out = self._bulk_transfer([0xc2, 0x5c, 0x37, 0x00, 0x00], 42)
        self.spyderData['serNo'] = out[9:17].tobytes().decode()

    def _get_factory_calibration(self):
        out = self._bulk_transfer([0xcb, 0x05, 0x73, 0x00, 0x01, 0x00], 47)
        print(f"Factory calibration raw data: {out}")
        out = out[5:]  # Remove first 5 bytes as in MATLAB code

        matrix = np.zeros((3, 3))
        v1 = out[1]  # MATLAB uses 1-based indexing, so this is correct
        v2 = self._read_nORD_be(out[2:4])
        v3 = out[40]  # 41 in MATLAB, but 40 in 0-based Python indexing

        for i in range(3):
            for j in range(3):
                k = i * 3 + j
                matrix[i, j] = self._read_IEEE754(out[k*4+4:k*4+8])  # +4 because MATLAB starts at 5

        self.spyderData['calibration'] = {
            'matrix': matrix,
            'v1': v1,
            'v2': v2,
            'v3': v3,
            'ccmat': np.eye(3)  # This is diag([1 1 1]) in MATLAB
        }
        print(f"Calibration data: {self.spyderData['calibration']}")

    @staticmethod
    def _read_nORD_be(input_bytes):
        return int.from_bytes(input_bytes, byteorder='big')

    @staticmethod
    def _read_IEEE754(input_bytes):
        # Reverse the byte order as in MATLAB code
        input_bytes = input_bytes[::-1]
        
        # Convert to binary string
        binary = ''.join(f'{byte:08b}' for byte in input_bytes)
        
        sign = int(binary[0])
        exponent = int(binary[1:9], 2)
        fraction = int(binary[9:], 2) / 2**23

        return (-1)**sign * (1 + fraction) * 2**(exponent - 127)

    def _get_amb_measure(self):
        out = self._bulk_transfer([0xd4, 0xa1, 0xc5, 0x00, 0x02, 0x65, 0x10], 11)
        self.spyderData['amb'] = struct.unpack('>HHBB', out[5:])

    def _setup_measurement(self):
        out = self._bulk_transfer([0xc3, 0x29, 0x27, 0x00, 0x01, self.spyderData['calibration']['v1']], 15)
        self.spyderData['settUp'] = {
            's1': out[5],
            's2': out[6:10],
            's3': out[10:14]
        }

    def calibrate(self):
        if not self.spyderData.get('isOpen', False):
            self.initialize()

        self._control_transfer(0x41, 2, 2, 0, None)
        v2 = self.spyderData['calibration']['v2']
        s1 = self.spyderData['settUp']['s1']
        s2 = self.spyderData['settUp']['s2']

        send = bytes([v2 >> 8, v2 & 0xFF, s1] + list(s2))
        out = self._bulk_transfer([0xd2, 0x3f, 0xb9, 0x00, 0x07] + list(send), 13)
        raw = struct.unpack('>HHHH', out[5:])
        self.spyderData['bcal'] = np.array(raw[:3]) - np.array(self.spyderData['settUp']['s3'][:3])
        self.spyderData['isBlackCal'] = True

    def measure(self):
        if not self.spyderData.get('isOpen', False):
            raise ValueError("SpyderX not initialized")
        if not self.spyderData.get('isBlackCal', False):
            raise ValueError("Black calibration not performed")

        self._control_transfer(0x41, 2, 2, 0, None)
        v2 = self.spyderData['calibration']['v2']
        s1 = self.spyderData['settUp']['s1']
        s2 = self.spyderData['settUp']['s2']

        send = bytes([v2 >> 8, v2 & 0xFF, s1] + list(s2))
        out = self._bulk_transfer([0xd2, 0x3f, 0xb9, 0x00, 0x07] + list(send), 13)
        print(out)
        raw = np.array(struct.unpack('>HHHH', out[5:]))
        print(raw)


        raw[:3] = raw[:3] - np.array(self.spyderData['settUp']['s3'][:3]) - self.spyderData['bcal']
        print(raw[:3])
        print(self.spyderData['calibration']['matrix'])
        XYZ = np.dot(raw[:3], self.spyderData['calibration']['matrix'])
        return XYZ

    def close(self):
        if self.dev:
            usb.util.dispose_resources(self.dev)
        self.spyderData['isOpen'] = False

def xyz_to_lms(xyz):
    # XYZ to LMS conversion matrix (Hunt-Pointer-Estevez)
    xyz_to_lms_matrix = np.array([
        [0.4002, 0.7076, -0.0808],
        [-0.2263, 1.1653, 0.0457],
        [0.0, 0.0, 0.9182]
    ])
    return np.dot(xyz_to_lms_matrix, xyz)

def main():
    spyder = SpyderX()
    try:
        print("Initializing SpyderX...")
        if spyder.initialize():
            print("Performing black calibration...")
            spyder.calibrate()
            print("Starting measurements...")
            while True:
                xyz = spyder.measure()
                lms = xyz_to_lms(xyz)
                print(f"XYZ values: {xyz}")
                print(f"LMS values: {lms}")
                time.sleep(2)
        else:
            print("Failed to initialize SpyderX. Please check the connection and try again.")
    except KeyboardInterrupt:
        print("\nMeasurement stopped by user.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise e
    finally:
        spyder.close()
        print("SpyderX closed.")

if __name__ == "__main__":
    main()