# Cleanup Plan for Dockable Widgets Refactoring

This document outlines the steps needed to clean up the codebase after the dockable widgets refactoring before merging back to the main branch.

## Priority Tasks

### 1. Entry Point Refactoring

- [ ] Rename `test_widgets_launch.py` to `app.py` or another appropriate name
- [ ] Update `main.py` to properly reference the new entry point
- [ ] Add proper command-line argument handling in the new entry point

### 2. Remove Unused Legacy Code

- [ ] Identify which components in `/components` are fully migrated to widgets
- [ ] Create a list of files that can be safely removed
- [ ] Comment out rather than delete initially, to ensure nothing breaks
- [ ] Remove commented-out code after thorough testing

### 3. Fix Any Remaining Bugs in Docking System

- [ ] Test all docking operations thoroughly (drag/drop, tabs, splits)
- [ ] Verify layout persistence works correctly (save/load)
- [ ] Check that the Exchange menu populates correctly
- [ ] Ensure all menu items trigger the appropriate actions

## Medium Priority Tasks

### 4. Code Duplication and Refactoring

- [ ] Identify duplicated code between old and new systems
- [ ] Refactor shared functionality into utility classes/functions
- [ ] Clean up any temporary workarounds in the implementation

### 5. Update Documentation

- [ ] Update docstrings in all new/modified files
- [ ] Make sure README.md reflects the new architecture
- [ ] Add developer documentation about how to create new widget types

### 6. Testing

- [ ] Write tests for the widget system
- [ ] Test on different platforms (Windows, Mac, Linux)
- [ ] Test with different screen resolutions and DPI settings

## Low Priority Tasks

### 7. UI Polishing

- [ ] Review widget default sizes and adjust as needed
- [ ] Add any missing keyboard shortcuts
- [ ] Consider adding tooltips for docking operations
- [ ] Implement a "first-run" tutorial for new users

### 8. Performance Optimization

- [ ] Profile the application with multiple widgets open
- [ ] Check for memory leaks when creating/destroying widgets
- [ ] Optimize any inefficient code paths

## Merge Strategy

1. Complete all Priority Tasks before merging
2. Create a PR with detailed description of all changes
3. Have at least one team member review the changes
4. Test the merged code thoroughly in a staging environment
5. Deploy to production

## Timeline

- Priority Tasks: 1-2 days
- Medium Priority: 2-3 days
- Low Priority: As time permits after merge

## Responsible Team Members

- Main Refactor: [Assign Name]
- Code Review: [Assign Name]
- Testing: [Assign Name] 