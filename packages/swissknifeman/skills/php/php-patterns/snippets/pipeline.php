<?php
final class Pipeline { public function through(array $pipes, mixed $passable): mixed { foreach ($pipes as $pipe) { $passable = $pipe($passable); } return $passable; } }
