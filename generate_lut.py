import pygame
import numpy as np
import time
from spyderx import SpyderX
import argparse
# Initialize Pygame
pygame.init()

# Set up the display
WIDTH, HEIGHT = 800, 800
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("RGB to LMS LUT Generator")

def wait_for_enter():
    screen.fill((255, 255, 255))  # Fill screen with white
    font = pygame.font.Font(None, 36)
    text = font.render("Position SpyderX and click to start", True, (0, 0, 0))
    text_rect = text.get_rect(center=(WIDTH/2, HEIGHT/2))
    screen.blit(text, text_rect)
    pygame.display.flip()

    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    waiting = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                waiting = False
        
    return True

def generate_lut(resolution=16):
    lut = {}
    spyder = SpyderX()
    spyder.initialize()

    total_colors = resolution ** 3
    current_color = 0

    if not wait_for_enter():
        spyder.close()
        return None
    
    screen.fill((0, 0, 0))
    pygame.display.flip()
    time.sleep(1)
    spyder.calibrate()

    for r in range(resolution):
        for g in range(resolution):
            for b in range(resolution):
                # Convert to 0-255 range
                r_255 = int(r * 255 / (resolution - 1))
                g_255 = int(g * 255 / (resolution - 1))
                b_255 = int(b * 255 / (resolution - 1))

                # Fill the screen with the color
                screen.fill((r_255, g_255, b_255))
                pygame.display.flip()

                # Wait for the display to update and the measurement to stabilize
                time.sleep(0.25)

                # Measure LMS
                xyz = spyder.measure()
                lms = xyz_to_lms(xyz)

                # Store in LUT
                lut[(r, g, b)] = lms

                # Update progress
                current_color += 1
                print(f"Progress: {current_color}/{total_colors} colors measured")

                # Handle Pygame events to keep the window responsive
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        spyder.close()
                        return lut

    spyder.close()
    pygame.quit()
    return lut

def xyz_to_lms(xyz):
    # XYZ to LMS conversion matrix (Hunt-Pointer-Estevez)
    xyz_to_lms_matrix = np.array([
        [0.4002, 0.7076, -0.0808],
        [-0.2263, 1.1653, 0.0457],
        [0.0, 0.0, 0.9182]
    ])
    return np.dot(xyz_to_lms_matrix, xyz)

def save_lut(lut, filename='rgb_to_lms_lut.npy'):
    np.save(filename, lut)
    print(f"LUT saved to {filename}")

def main():
    parser = argparse.ArgumentParser(description="RGB to LMS LUT Generator")
    parser.add_argument('-r', '--resolution', type=int, default=16, help="LUT resolution (default: 16)")
    parser.add_argument('-o', '--output_file', type=str, default='rgb_to_lms_lut.npy', help="Output file name (default: rgb_to_lms_lut.npy)")
    
    args = parser.parse_args()

    lut = generate_lut(resolution=args.resolution)
    if lut:
        save_lut(lut, filename=args.output_file)

if __name__ == "__main__":
    main()