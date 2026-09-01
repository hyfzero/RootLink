import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/app_state.dart';
import '../../domain/models.dart';

class RoleAvatar extends ConsumerWidget {
  const RoleAvatar({
    super.key,
    required this.role,
    this.radius = 28,
    this.expression,
  });

  final CompanionRole role;
  final double radius;
  final String? expression;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final path = expression == null
        ? role.avatarPath
        : (role.portraits[expression] ?? role.standingImagePath).toString();
    final file = ref.read(dependenciesProvider).roles.resolveAsset(role, path);
    final fallback = Container(
      color: Theme.of(context).colorScheme.primaryContainer,
      alignment: Alignment.center,
      child: Text(
        role.name.isEmpty ? 'R' : role.name.characters.first,
        style: TextStyle(
          color: Theme.of(context).colorScheme.onPrimaryContainer,
          fontSize: radius * 0.72,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
    return ClipOval(
      child: SizedBox.square(
        dimension: radius * 2,
        child: file == null || !file.existsSync()
            ? fallback
            : Image.file(
                File(file.path),
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) => fallback,
              ),
      ),
    );
  }
}

class StandingPortrait extends ConsumerWidget {
  const StandingPortrait({
    super.key,
    required this.role,
    required this.expression,
  });

  final CompanionRole role;
  final String expression;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final relative = (role.portraits[expression] ?? role.standingImagePath)
        .toString();
    final file = ref
        .read(dependenciesProvider)
        .roles
        .resolveAsset(role, relative);
    if (file == null || !file.existsSync()) {
      return Center(child: RoleAvatar(role: role, radius: 76));
    }
    return Image.file(
      file,
      fit: BoxFit.contain,
      alignment: Alignment.bottomCenter,
      errorBuilder: (context, error, stackTrace) =>
          Center(child: RoleAvatar(role: role, radius: 76)),
    );
  }
}
