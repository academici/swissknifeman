<?php
namespace App\Policies;

final class PostPolicy
{
    public function update(object $user, object $post): bool { return $user->id === $post->user_id; }
}
