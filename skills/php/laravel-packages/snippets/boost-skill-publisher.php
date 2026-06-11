<?php
// Laravel Boost: publish skills via vendor:publish
$this->publishes([
    __DIR__.'/../../skills' => base_path('.ai/skills/vendor'),
], 'skills');
