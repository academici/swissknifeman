<?php
use Illuminate\Support\Facades\Gate;
Gate::define('manage-settings', fn ($user) => $user->isAdmin());
