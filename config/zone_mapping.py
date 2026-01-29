"""Zone to light mapping management."""

import json
from pathlib import Path
from typing import Dict, List, Optional


class ZoneMapping:
    def __init__(self):
        self.mapping: Dict[str, List[str]] = {}
                
        self._set_default_mapping()

    def _set_default_mapping(self):
        """Set default zone mappings for ambilight layout."""
        self.mapping = {
            'top_0': [],
            'top_1': [],
            'top_2': [],
            'bottom_0': [],
            'bottom_1': [],
            'bottom_2': [],
            'left_0': [],
            'left_1': [],
            'right_0': [],
            'right_1': []
        }

    def map_zone_to_lights(self, zone_id: str, light_ids: List[str]):
        """Assign lights to a zone."""
        self.mapping[zone_id] = light_ids

    def get_lights_for_zone(self, zone_id: str) -> List[str]:
        """Get lights assigned to a zone."""
        return self.mapping.get(zone_id, [])

    def get_all_zones(self) -> List[str]:
        """Get all zone IDs."""
        return list(self.mapping.keys())

    def generate_ambilight_mapping(self, available_lights: List[str],
                                    light_info: Optional[Dict[str, dict]] = None,
                                    top_count: int = 3,
                                    bottom_count: int = 3,
                                    left_count: int = 2,
                                    right_count: int = 2):
        """Auto-generate ambilight zone mapping with smart hardware awareness.

        Uses light archetype and names to intelligently place lightstrips on the 
        top and play bars on the sides.
        """
        self.mapping = {}

        # Initialize all potential zones
        for i in range(top_count): self.mapping[f"top_{i}"] = []
        for i in range(bottom_count): self.mapping[f"bottom_{i}"] = []
        for i in range(left_count): self.mapping[f"left_{i}"] = []
        for i in range(right_count): self.mapping[f"right_{i}"] = []

        if not available_lights:
            return

        edge_counts = {
            'top': top_count,
            'bottom': bottom_count,
            'left': left_count,
            'right': right_count
        }

        # Step 1: Sort and categorize lights
        # Priorities: Strips -> Top, Bars -> Sides
        bins = {'top': [], 'bottom': [], 'left': [], 'right': []}
        
        # Sort available lights to have some deterministic order if no info
        sorted_lights = sorted(available_lights)
        
        if not light_info:
            # Fallback to simple round-robin if no hardware info
            order = ['left', 'top', 'right', 'bottom']
            for i, light_id in enumerate(sorted_lights):
                edge = order[i % len(order)]
                bins[edge].append(light_id)
        else:
            print(f"Generating Ambilight mapping for {len(sorted_lights)} lights...")
            coord_count = sum(1 for lid in sorted_lights if light_info.get(lid, {}).get('position'))
            print(f"Lights with spatial coordinates: {coord_count}")

            # Step 1: Assign lights to bins based solely on X/Z coordinates
            for lid in sorted_lights:
                info = light_info.get(lid, {}) if light_info else {}
                pos = info.get('position')
                if not pos:
                    continue
                
                is_gradient = info.get('is_gradient', False)
                name = str(info.get('name', lid)).lower()
                arch = str(info.get('archetype', '')).lower()
                
                x, z = pos.get('x', 0), pos.get('z', 0)
                
                # Height-based assignment (Top/Bottom)
                if z > 0.4: # Definitely Top
                    bins['top'].append(lid)
                elif z < -0.3: # Definitely Bottom
                    bins['bottom'].append(lid)
                elif x < -0.4: # Far Left
                    bins['left'].append(lid)
                elif x > 0.4: # Far Right
                    bins['right'].append(lid)
                else: # Central/Upper area
                    bins['top'].append(lid)
                
                # Special Case: Gradient strips in the upper area typically wrap
                if is_gradient and z > -0.2 and ('strip' in arch or 'strip' in name):
                    # Ensure it's in all 3 if not already
                    if lid not in bins['left']: bins['left'].append(lid)
                    if lid not in bins['top']: bins['top'].append(lid)
                    if lid not in bins['right']: bins['right'].append(lid)

        # Step 2: Assign lights in each bin to the zones on that edge
        for edge_name, lights in bins.items():
            count = edge_counts[edge_name]
            if not lights:
                continue
            
            for i, light_id in enumerate(lights):
                info = light_info.get(light_id, {}) if light_info else {}
                is_gradient = info.get('is_gradient', False)
                pos = info.get('position')
                
                if is_gradient:
                    # Gradient lights map to all zones on this edge
                    for z_idx in range(count):
                        zone_id = f"{edge_name}_{z_idx}"
                        if zone_id not in self.mapping: self.mapping[zone_id] = []
                        if light_id not in self.mapping[zone_id]: self.mapping[zone_id].append(light_id)
                else:
                    # For normal lights, if we have coordinates, map to the closest zone index
                    if pos and edge_name in ['top', 'bottom']:
                        x = pos.get('x', 0)
                        # Map x [-1, 1] to zone index [0, count-1]
                        zone_idx = int((x + 1) / 2 * count)
                        zone_idx = max(0, min(count - 1, zone_idx))
                    elif pos and edge_name in ['left', 'right']:
                        z = pos.get('z', 0)
                        # Map z [1, -1] (top down) to [0, count-1]
                        zone_idx = int((1 - z) / 2 * count)
                        zone_idx = max(0, min(count - 1, zone_idx))
                    else:
                        zone_idx = int((i + 0.5) * count / len(lights))
                        
                    zone_id = f"{edge_name}_{zone_idx}"
                    if zone_id not in self.mapping: self.mapping[zone_id] = []
                    if light_id not in self.mapping[zone_id]: self.mapping[zone_id].append(light_id)

    def validate_mapping(self, available_lights: List[str]) -> List[str]:
        """Validate zone mapping and return list of invalid lights.

        Args:
            available_lights: List of available light IDs

        Returns:
            List of light IDs that are not available on the bridge
        """
        invalid_lights = []
        available_set = set(available_lights)

        for zone_id, light_ids in self.mapping.items():
            for light_id in light_ids:
                if light_id not in available_set:
                    invalid_lights.append(light_id)

        return invalid_lights
