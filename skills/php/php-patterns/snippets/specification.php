<?php
interface Specification { public function isSatisfiedBy(object $candidate): bool; }
