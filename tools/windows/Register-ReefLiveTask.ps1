<#
Registers the Windows scheduled task that runs the Reef live-paper runner after the US market closes.

DEFAULT IS A DRY RUN: it prints the task and changes nothing. Do not pass -Install until unattended running is approved.
The runner is safe to run repeatedly: it does nothing until a session's data is final, and it catches up missed sessions in order.

  .\tools\windows\Register-ReefLiveTask.ps1                 # dry run
  .\tools\windows\Register-ReefLiveTask.ps1 -Install        # create the task (needs approval)
  .\tools\windows\Register-ReefLiveTask.ps1 -Remove         # delete it

Local time zone note: the market closes 4:00 pm New York (1:00 pm on early-close days). -StartTime is LOCAL time;
the default 14:15 suits US Mountain. The task repeats every 30 minutes for 6 hours so late vendor data is picked up.
#>
param(
    [switch]$Install,
    [switch]$Remove,
    [string]$StartTime = "14:15",
    [string]$Repo = (Resolve-Path "$PSScriptRoot\..\..").Path
)
$TaskName = "ReefLiveDaily"
$uv = (Get-Command uv -ErrorAction Stop).Source
$action = New-ScheduledTaskAction -Execute $uv -Argument "run --group data python tools/live.py run" -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $StartTime
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $StartTime -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Hours 6)).Repetition
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

if ($Remove) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false; Write-Host "removed $TaskName"; exit 0 }
Write-Host "Task      : $TaskName"
Write-Host "Command   : $uv run --group data python tools/live.py run   (in $Repo)"
Write-Host "Schedule  : Mon-Fri $StartTime local, every 30 min for 6 h; runs missed starts when the PC wakes"
Write-Host "Paper only: no broker, no paid service; exit codes 2 (SAFE_HOLD) and 3 (waiting) are visible in Task Scheduler history"
if (-not $Install) { Write-Host "`nDRY RUN: nothing was installed. Re-run with -Install once approved."; exit 0 }
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Reef live-data paper epoch (paper money only)" | Out-Null
Write-Host "installed $TaskName"
